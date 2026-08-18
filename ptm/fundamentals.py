"""The fundamentals table, built from EDGAR only.

Every number the screen runs on comes from SEC filings. yfinance supplies price
history and nothing else — no `info` snapshot, no analyst targets, no
recommendation, no Yahoo earnings calendar. Those were a live snapshot with no
history behind them, which made them unusable for a backdated run and merely
opaque for a live one.

What comes from where:

| Field           | Source                                                    |
|-----------------|-----------------------------------------------------------|
| price           | last close at or before the run date (prices.csv)          |
| shares          | latest share count filed by the run date (XBRL)            |
| market_cap      | shares x that close                                        |
| trailing_eps    | TTM diluted EPS from filings public by the run date (XBRL)  |
| trailing_pe     | price / trailing_eps — exact, no estimate involved          |
| forward_eps     | management guidance in the 8-K release, else extrapolated   |
| earnings_growth | realized TTM over prior TTM, or guidance over trailing      |
| earnings_date   | projected from filing cadence (informational; the idea
|                 | pipeline re-resolves it via ptm/earnings.py for provenance) |
| sector/industry | the index membership tables, not a data vendor              |

The only thing EDGAR cannot supply is **analyst consensus**: it is proprietary
and never appears in a filing. See docs/FEATURE-LIMITATIONS.md.
"""

from __future__ import annotations

import time
from datetime import date

import pandas as pd

from ptm.asof import as_of_date, is_backdated
from ptm.backdate import close_on, next_report_estimate
from ptm.config import data_dir, toml_settings
from ptm.io import read_df, write_df
from ptm.log import elapsed_since, eta, log

CHECKPOINT_EVERY = 25


def _cfg() -> dict:
    return toml_settings().get("edgar") or {}


def _load_prices() -> pd.DataFrame:
    path = data_dir("curated", "prices.csv")
    if not path.exists():
        return pd.DataFrame()
    frame = read_df(path)
    frame.columns = [str(c).lower() for c in frame.columns]
    return frame


def row_for(
    ticker: str,
    name: str,
    sector: str,
    industry: str,
    prices: pd.DataFrame,
    upto: date,
    with_guidance: bool = True,
) -> dict:
    """One fundamentals row: EDGAR facts priced at the run date's close."""
    from ptm.ingest.edgar import company_fundamentals

    facts = company_fundamentals(ticker, with_guidance=with_guidance)
    price = close_on(prices, ticker, upto)
    shares = facts.get("shares")
    eps0 = facts.get("eps_ttm")
    prior = facts.get("eps_prior_ttm")

    growth = None
    clamped = False
    if eps0 is not None and prior not in (None, 0) and prior > 0:
        growth = eps0 / prior - 1.0
        # A tiny or one-off prior year turns the ratio into nonsense: Alcoa
        # showed +300%, which extrapolated to a forward EPS four times trailing
        # and would have screened as absurdly cheap. Cap it and say so.
        cap = float(_cfg().get("max_extrapolated_growth", 0.5))
        if abs(growth) > cap:
            growth = cap if growth > 0 else -cap
            clamped = True

    # Forward EPS, best available source first. Neither is analyst consensus,
    # which has no free source at all, point-in-time or otherwise.
    guidance = facts.get("guidance") or None
    if guidance and guidance.get("midpoint"):
        eps1 = float(guidance["midpoint"])
        forward_source = "management_guidance"
        forward_basis = (
            "company guidance in the 8-K earnings release (ADJUSTED basis; not comparable "
            f"with GAAP trailing EPS): {str(guidance.get('quote'))[:140]}"
        )
        if eps0 and eps0 > 0:
            growth = eps1 / eps0 - 1.0
    elif eps0 is not None and growth is not None:
        eps1 = eps0 * (1.0 + growth)
        forward_source = "extrapolated_clamped" if clamped else "extrapolated"
        forward_basis = (
            f"realized TTM growth clamped to {growth:+.0%} before extrapolating "
            "(raw rate was distorted)"
            if clamped
            else "extrapolated realized TTM growth (not consensus, not guidance)"
        )
    else:
        eps1 = eps0
        forward_source = "flat"
        forward_basis = "no growth signal; forward EPS held flat at trailing"

    next_report, cadence_note = next_report_estimate(facts.get("report_dates") or [], upto)
    trailing_pe = (price / eps0) if (price and eps0) else None
    return {
        "ticker": ticker,
        "name": name or ticker,
        "sector": sector or "",
        "industry": industry or "",
        "price": price,
        "market_cap": (shares * price) if (shares and price) else None,
        "forward_eps": eps1,
        "trailing_eps": eps0,
        "forward_pe": (price / eps1) if (price and eps1) else None,
        "trailing_pe": trailing_pe,
        "earnings_growth": growth,
        "shares": shares,
        "earnings_date": next_report,
        "revenue": facts.get("revenue"),
        "net_income": facts.get("net_income"),
        "ebit": facts.get("ebit"),
        "cash": facts.get("cash"),
        "debt": facts.get("debt"),
        "source": "edgar",
        "eps_basis": facts.get("eps_basis"),
        "last_period_end": facts.get("last_period_end"),
        "trailing_pe_exact": trailing_pe is not None,
        "forward_source": forward_source,
        "forward_basis": forward_basis,
        "earnings_date_basis": cadence_note,
        "as_of": upto.isoformat(),
    }


def build_fundamentals(
    universe: pd.DataFrame,
    upto: date | None = None,
    force: bool = False,
    with_guidance: bool | None = None,
) -> pd.DataFrame:
    """Build (or backfill) the fundamentals table for a universe.

    Rows already present are reused unless `force`, so a capped smoke run
    followed by a full run only fetches the difference.
    """
    upto = upto or as_of_date()
    if with_guidance is None:
        with_guidance = bool(_cfg().get("fetch_guidance", True))
    path = data_dir("curated", "yahoo_fundamentals.csv")
    prices = _load_prices()
    tickers = [str(t) for t in universe["ticker"].tolist() if t]

    cached = pd.DataFrame()
    if path.exists() and not force:
        try:
            cached = read_df(path)
        except Exception as exc:
            log(f"fundamentals: unreadable cache ({exc}); rebuilding")
    have: set[str] = set()
    if not cached.empty and "ticker" in cached.columns:
        # A cache from a different run date describes a different world.
        if "as_of" in cached.columns:
            cached = cached[cached["as_of"].astype(str) == upto.isoformat()]
        if not cached.empty:
            have = set(cached["ticker"].astype(str))
    missing = [t for t in tickers if t not in have]
    log(
        f"fundamentals (EDGAR): {len(have)} cached / {len(tickers)} universe; "
        f"{len(missing)} to fetch  guidance={'on' if with_guidance else 'off'}"
    )
    if not missing:
        return cached[cached["ticker"].astype(str).isin(tickers)]

    lookup = universe.set_index("ticker") if "ticker" in universe.columns else universe
    started = time.monotonic()
    records: list[dict] = []
    for i, ticker in enumerate(missing, start=1):
        try:
            meta = lookup.loc[ticker] if ticker in lookup.index else None
        except Exception:
            meta = None

        def _field(key: str) -> str:
            if meta is None:
                return ""
            value = meta[key] if key in getattr(meta, "index", []) else ""
            if isinstance(value, pd.Series):
                value = value.iloc[0]
            return "" if pd.isna(value) else str(value)

        try:
            record = row_for(
                ticker,
                _field("name"),
                _field("sector"),
                _field("industry"),
                prices,
                upto,
                with_guidance=with_guidance,
            )
        except Exception as exc:
            log(f"fundamentals {i}/{len(missing)} {ticker} FAIL {exc}")
            record = {
                "ticker": ticker,
                "name": _field("name") or ticker,
                "sector": _field("sector"),
                "industry": _field("industry"),
                "source": "edgar",
                "eps_basis": f"failed: {exc}",
                "as_of": upto.isoformat(),
            }
        records.append(record)
        if i % CHECKPOINT_EVERY == 0 or i == len(missing):
            merged = _merge(cached, pd.DataFrame(records), path)
            log(
                f"fundamentals {i}/{len(missing)} {ticker}  rows {len(merged)}  "
                f"elapsed {elapsed_since(started)}  eta {eta(i, len(missing), started)}"
            )
    frame = _merge(cached, pd.DataFrame(records), path)
    usable = int(frame["trailing_eps"].notna().sum()) if "trailing_eps" in frame.columns else 0
    log(f"fundamentals done: {len(frame)} rows, {usable} with EPS from filings, in {elapsed_since(started)}")
    return frame[frame["ticker"].astype(str).isin(tickers)]


def _merge(cached: pd.DataFrame, fresh: pd.DataFrame, path) -> pd.DataFrame:
    if fresh.empty:
        combined = cached
    elif cached.empty:
        combined = fresh
    else:
        combined = pd.concat([cached, fresh], ignore_index=True)
    if combined.empty:
        return combined
    combined = combined.drop_duplicates(subset=["ticker"], keep="last")
    write_df(path, combined)
    return combined


def source_warnings(frame: pd.DataFrame) -> list[str]:
    """Caveats that apply to every run, not only backdated ones."""
    warnings: list[str] = []
    if frame is None or frame.empty:
        return ["No fundamentals were built."]
    total = len(frame)
    if "forward_source" in frame.columns:
        counts = frame["forward_source"].value_counts().to_dict()
        warnings.append(
            "Forward EPS is not analyst consensus (EDGAR holds filings, not estimates): "
            f"{int(counts.get('management_guidance', 0))} from company guidance, "
            f"{int(counts.get('extrapolated', 0))} extrapolated from realized growth, "
            f"{int(counts.get('extrapolated_clamped', 0))} extrapolated with a clamped growth rate, "
            f"{int(counts.get('flat', 0))} held flat. Trailing P/E is exact."
        )
    if "trailing_eps" in frame.columns:
        have = int(frame["trailing_eps"].notna().sum())
        if have < 0.8 * total:
            warnings.append(
                f"Only {have}/{total} names had usable EPS in their XBRL filings; "
                "the P/E screen is thinner than the universe suggests."
            )
    if "price" in frame.columns:
        priced = int(frame["price"].notna().sum())
        if priced < 0.9 * total:
            warnings.append(f"Only {priced}/{total} names had a close on the run date.")
    if is_backdated():
        warnings.append(
            "BACKDATED RUN: index membership comes from today's constituent lists, so the "
            "universe carries survivorship and membership drift."
        )
        warnings.append(
            "BACKDATED RUN: the next-earnings date is projected from filing cadence, not "
            "the calendar as published then."
        )
    return warnings
