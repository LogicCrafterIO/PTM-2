"""What the market already expects, so a thesis can be judged against it.

The screen finds a P/E far from its sector and the verdict asks whether the
operating evidence explains the gap. Nothing ever asked what the market has
already assumed - and a discount multiple exists *because* the market already
believes bad things. Listing more bad things does not make a trade; it may only
restate consensus. Measured on one full run, 4 of 323 evidence items (1.2%)
referred to market expectations at all, and three independent reviews of the
resulting book converged on the same complaint: a valuation argument was being
converted into an earnings-event trade without establishing what was priced.

Four measures, each answering a different half of that question:

* **Implied move** - the magnitude the options market is pricing into the print.
  The book is expressed in options, so this is the thesis's actual hurdle: a
  correct call on a name pricing a 3% move pays very little.
* **Estimate revisions** - which way consensus has already travelled. A short
  whose estimates are being cut is a story the market is already telling.
* **Past-print reactions** - whether the market has already punished this story.
  Computed offline from prices already on disk; no network call.
* **Surprise history** - whether this name habitually beats or misses.

**Vintage.** None of the four has a point-in-time archive. Options chains, the
revisions table and the surprise table all describe today and cannot be rolled
back, so a backdated run refuses them outright - the same rule, and the same
reason, as `ptm/ingest/estimates.py`. Live and backdated runs therefore differ
in what the verdict sees. That asymmetry is the accepted cost of measuring
expectations at all; see docs/FEATURE-LIMITATIONS.md.

**Why this is not EDGAR.** Filings state what a company reported. Expectations
are by definition what it has not reported yet. Like consensus EPS, this is a
requirement the EDGAR-only rule structurally cannot meet.
"""

from __future__ import annotations

import time
from datetime import date, datetime, timezone
from functools import lru_cache

from ptm.asof import as_of_date, is_backdated
from ptm.config import data_dir, toml_settings
from ptm.io import read_json, write_json
from ptm.log import log

PERIOD_CURRENT = "0y"


def _cfg() -> dict:
    return toml_settings().get("expectations") or {}


def enabled() -> bool:
    return bool(_cfg().get("enabled", True))


def _max_age_days() -> int:
    return int(_cfg().get("max_age_days") or 2)


def _thin_open_interest() -> int:
    return int(_cfg().get("thin_open_interest") or 100)


def _wide_spread_pct() -> float:
    return float(_cfg().get("wide_spread_pct") or 25.0)


def _cache_fresh(path) -> bool:
    if not path.exists():
        return False
    max_age = _max_age_days()
    if max_age <= 0:
        return True
    return (time.time() - path.stat().st_mtime) / 86400.0 <= max_age


def _num(value) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return None if out != out else out  # drop NaN


# --- implied move -------------------------------------------------------------


def _mid(row) -> tuple[float | None, float | None]:
    """Mid price and relative spread for one option row.

    `lastPrice` is deliberately not the first choice. On an illiquid chain the
    last trade can be days old, and a stale last produces a confident-looking
    implied move that is simply wrong - one book name showed a 3.4% move off a
    last with no bid or ask behind it. Mid is used where a two-sided market
    exists, and the caller is told when it does not.
    """
    bid, ask = _num(row.get("bid")), _num(row.get("ask"))
    if bid and ask and ask >= bid > 0:
        mid = (bid + ask) / 2.0
        spread = (ask - bid) / mid * 100.0 if mid else None
        return mid, spread
    last = _num(row.get("lastPrice"))
    return (last if last and last > 0 else None), None


def _chain_liquidity(calls, puts) -> dict:
    """Liquidity of the whole chain, not of one strike.

    The first version of this read open interest and the bid/ask off the single
    at-the-money row and called the chain thin whenever that row was blank. That
    was wrong, and confidently so - it flagged 11 of 12 book names. POWL carries
    **319** contracts of open interest across 125 strikes, but only 28 of those
    strikes quote two-sided at any moment, and the strike nearest spot is
    usually not one of them. A blank row says nothing about the chain.

    Liquidity is therefore measured in aggregate: total open interest, and how
    many strikes are actually quotable.
    """
    out = {"open_interest": 0, "two_sided_strikes": 0, "strikes": 0, "volume": 0}
    for frame in (calls, puts):
        if frame is None or getattr(frame, "empty", True):
            continue
        try:
            out["strikes"] += len(frame)
            if "openInterest" in frame:
                out["open_interest"] += int(frame["openInterest"].fillna(0).sum())
            if "volume" in frame:
                out["volume"] += int(frame["volume"].fillna(0).sum())
            if "bid" in frame and "ask" in frame:
                out["two_sided_strikes"] += int(
                    ((frame["bid"].fillna(0) > 0) & (frame["ask"].fillna(0) > 0)).sum()
                )
        except Exception:
            continue
    return out


# A listed chain this wide cannot genuinely carry zero open interest. Open
# interest is a settled, persistent figure - unlike volume, which is legitimately
# zero outside the session - so zero across this many strikes is the feed
# failing to populate the field.
MIN_STRIKES_FOR_OI = 10


def _open_interest_missing(liquidity: dict) -> bool:
    """Did the feed simply not return open interest?

    Worth being blunt about how this was found. Reading it off one strike
    flagged 11 of 12 book names as thin. Reading it across the chain still put
    **ABNB and ANET at zero** - two of the most liquid option chains in the US
    market - alongside 39 others. yfinance returns this field for some tickers
    and zeros it for others in the same batch, and there is no way to tell from
    a single response which happened.

    So the answer is "unknown", not "thin". Anything else asserts illiquidity
    from missing data, which is how this check was wrong twice.
    """
    return liquidity.get("open_interest", 0) == 0 and liquidity.get("strikes", 0) >= MIN_STRIKES_FOR_OI


# How far from spot a strike may sit and still price a usable straddle. Beyond
# this the straddle stops being at-the-money and the implied move is distorted.
ATM_BAND_PCT = 10.0


def _pick_straddle(calls, puts, spot: float) -> tuple[dict, dict, str]:
    """The nearest strike that both legs actually quote, else nearest to spot.

    Preferring a quoted strike matters more than preferring the exact ATM one:
    a mid from a strike 2% away is a real price, while `lastPrice` at the money
    can be days stale. Searching outward from spot but refusing to leave
    ATM_BAND_PCT keeps the straddle at-the-money enough to mean something.
    """
    call_by_strike = {float(r["strike"]): r for r in calls.to_dict("records")}
    put_by_strike = {float(r["strike"]): r for r in puts.to_dict("records")}
    shared = sorted(set(call_by_strike) & set(put_by_strike), key=lambda k: abs(k - spot))
    if not shared:
        call = calls.iloc[(calls["strike"] - spot).abs().argsort()[:1]].iloc[0].to_dict()
        put = puts.iloc[(puts["strike"] - spot).abs().argsort()[:1]].iloc[0].to_dict()
        return call, put, "last_trade_only"
    for strike in shared:
        if abs(strike - spot) / spot * 100.0 > ATM_BAND_PCT:
            break
        call, put = call_by_strike[strike], put_by_strike[strike]
        if _mid(call)[1] is not None and _mid(put)[1] is not None:
            return call, put, "mid"
    nearest = shared[0]
    return call_by_strike[nearest], put_by_strike[nearest], "last_trade_only"


def implied_move(ticker: str, earnings_date: str | None = None) -> dict:
    """ATM straddle over spot, at the first expiry that covers the print.

    This is an approximation and is labelled as one: the straddle spans the
    whole expiry, so it carries non-earnings volatility too, and it overstates
    the event move by however much time sits either side of the print. It is the
    standard read, not a decomposed event move, and nothing here pretends
    otherwise.
    """
    import yfinance as yf

    out: dict = {"available": False, "reason": ""}
    handle = yf.Ticker(ticker)
    try:
        expiries = list(handle.options or [])
    except Exception as exc:
        out["reason"] = f"chain unavailable ({type(exc).__name__})"
        return out
    if not expiries:
        out["reason"] = "no listed options"
        return out
    target = (earnings_date or "")[:10] or date.today().isoformat()
    covering = [e for e in expiries if e >= target]
    expiry = covering[0] if covering else expiries[-1]
    out["expiry"] = expiry
    out["expiry_covers_earnings"] = bool(covering)
    out["expiries_listed"] = len(expiries)
    try:
        chain = handle.option_chain(expiry)
        spot = _num((handle.fast_info or {}).get("lastPrice"))
        if spot is None:
            spot = _num(handle.history(period="1d")["Close"].iloc[-1])
    except Exception as exc:
        out["reason"] = f"chain fetch failed ({type(exc).__name__})"
        return out
    if not spot:
        out["reason"] = "no spot price"
        return out
    calls, puts = chain.calls, chain.puts
    if calls.empty or puts.empty:
        out["reason"] = "empty chain"
        return out
    call, put, basis = _pick_straddle(calls, puts, spot)
    call_mid, call_spread = _mid(call)
    put_mid, put_spread = _mid(put)
    if call_mid is None or put_mid is None:
        out["reason"] = "no priced at-the-money straddle"
        return out
    spreads = [s for s in (call_spread, put_spread) if s is not None]
    liquidity = _chain_liquidity(calls, puts)
    spread_pct = round(sum(spreads) / len(spreads), 1) if spreads else None
    oi_missing = _open_interest_missing(liquidity)
    out.update(
        {
            "available": True,
            "spot": round(spot, 4),
            "strike": round(_num(call.get("strike")) or spot, 4),
            "strike_offset_pct": round((float(call.get("strike") or spot) / spot - 1) * 100.0, 2),
            "implied_move_pct": round((call_mid + put_mid) / spot * 100.0, 2),
            # Chain-level, not strike-level. See _chain_liquidity.
            "open_interest": liquidity["open_interest"],
            "two_sided_strikes": liquidity["two_sided_strikes"],
            "strikes": liquidity["strikes"],
            "spread_pct": spread_pct,
            "quote_basis": basis,
            "open_interest_missing": oi_missing,
            # None means "cannot tell", and is not the same as False. Two
            # market-hours artefacts had to be taken out of this test before it
            # meant anything: a chain with zero quotable strikes is normal
            # outside the session, and a chain reporting zero open interest
            # across dozens of strikes is a feed failure, not an empty market.
            "thin": None
            if oi_missing
            else (
                liquidity["open_interest"] < _thin_open_interest()
                or (spread_pct is not None and spread_pct > _wide_spread_pct())
            ),
        }
    )
    return out


# --- revisions and surprise ---------------------------------------------------


def revisions(ticker: str) -> dict:
    """Which way consensus has already moved, over 30 and 90 days."""
    import yfinance as yf

    out: dict = {"available": False}
    handle = yf.Ticker(ticker)
    try:
        trend = handle.eps_trend
        counts = handle.eps_revisions
    except Exception:
        return out
    current = up = down = None
    for column, key in (("current", "current"), ("30daysAgo", "d30"), ("90daysAgo", "d90")):
        try:
            value = _num(trend.loc[PERIOD_CURRENT, column])
        except Exception:
            value = None
        out[f"eps_{key}"] = value
    current = out.get("eps_current")
    for key, days in (("change_30d_pct", "eps_d30"), ("change_90d_pct", "eps_d90")):
        prior = out.get(days)
        out[key] = (
            round((current / prior - 1.0) * 100.0, 2)
            if current is not None and prior not in (None, 0)
            else None
        )
    try:
        up = _num(counts.loc[PERIOD_CURRENT, "upLast30days"])
        down = _num(counts.loc[PERIOD_CURRENT, "downLast30days"])
    except Exception:
        pass
    out["analysts_up_30d"] = int(up) if up is not None else None
    out["analysts_down_30d"] = int(down) if down is not None else None
    out["available"] = out.get("change_90d_pct") is not None or up is not None
    return out


def surprise_history(ticker: str, limit: int = 4) -> dict:
    """Whether this name habitually clears the bar it is set."""
    import yfinance as yf

    out: dict = {"available": False}
    try:
        frame = yf.Ticker(ticker).earnings_history
    except Exception:
        return out
    if frame is None or getattr(frame, "empty", True):
        return out
    rows = []
    for quarter, row in list(frame.iterrows())[-limit:]:
        # yfinance reports surprisePercent as a FRACTION (0.0923 = +9.23%).
        pct = _num(row.get("surprisePercent"))
        rows.append(
            {
                "quarter": str(quarter)[:10],
                "actual": _num(row.get("epsActual")),
                "estimate": _num(row.get("epsEstimate")),
                "surprise_pct": round(pct * 100.0, 2) if pct is not None else None,
            }
        )
    sized = [r["surprise_pct"] for r in rows if r["surprise_pct"] is not None]
    if not sized:
        return out
    return {
        "available": True,
        "prints": rows,
        "beats": sum(1 for v in sized if v > 0),
        "of": len(sized),
        "avg_surprise_pct": round(sum(sized) / len(sized), 2),
    }


# --- past-print price reaction (offline) --------------------------------------


@lru_cache(maxsize=1)
def _prices():
    from ptm.io import read_df

    path = data_dir("curated", "prices.csv")
    if not path.exists():
        return None
    frame = read_df(path)
    frame.columns = [str(c).lower() for c in frame.columns]
    return frame


def past_reactions(ticker: str, limit: int = 4) -> dict:
    """How the market moved on this name's recent reports.

    Uses prices and EDGAR report dates already on disk, so it costs no network
    call. Two honest caveats: these are 10-K/10-Q **filing** dates rather than
    8-K release dates - usually the same day or within a day or two for US
    issuers, but not guaranteed - and only about four prints fall inside the
    one-year price window the pipeline fetches.
    """
    out: dict = {"available": False}
    frame = _prices()
    if frame is None:
        return out
    dates_path = data_dir("raw", "edgar", f"{ticker}_reportdates.json")
    if not dates_path.exists():
        return out
    try:
        report_dates = [str(d)[:10] for d in (read_json(dates_path) or [])]
    except Exception:
        return out
    sub = frame[frame["ticker"] == ticker]
    if sub.empty or "date" not in sub.columns:
        return out
    sub = sub.sort_values("date")
    days = [str(d)[:10] for d in sub["date"].tolist()]
    closes = [_num(c) for c in sub["close"].tolist()]
    cutoff = as_of_date().isoformat()
    rows = []
    for report in report_dates:
        if report > cutoff:
            continue
        # First session on or after the filing, and the close before it.
        idx = next((i for i, d in enumerate(days) if d >= report), None)
        if idx is None or idx == 0:
            continue
        before, after = closes[idx - 1], closes[idx]
        if not before or not after:
            continue
        rows.append({"report_date": report, "move_pct": round((after / before - 1.0) * 100.0, 2)})
        if len(rows) >= limit:
            break
    if not rows:
        return out
    moves = [r["move_pct"] for r in rows]
    return {
        "available": True,
        "prints": rows,
        "avg_abs_move_pct": round(sum(abs(m) for m in moves) / len(moves), 2),
        "down_prints": sum(1 for m in moves if m < 0),
        "of": len(moves),
    }


# --- assembly -----------------------------------------------------------------


def _cache_path(ticker: str):
    return data_dir("raw", "expectations", f"{ticker}.json")


def expectations(ticker: str, earnings_date: str | None = None, force: bool = False) -> dict | None:
    """Directional revision and earnings-history context, or None.

    Returns None on a backdated run: these sources cannot be rolled
    back to a past vintage, and serving today's expectations to a historical run
    is exactly the lookahead the rest of the pipeline exists to prevent.

    Option-chain data is intentionally excluded. Yahoo's chain is not reliable
    enough to gate or rank ideas; live IV is assessed manually downstream.
    """
    if not enabled():
        return None
    if is_backdated():
        return None
    cache = _cache_path(ticker)
    if not force and _cache_fresh(cache):
        try:
            cached = read_json(cache)
            if isinstance(cached, dict):
                payload = {
                    key: cached.get(key)
                    for key in (
                        "ticker",
                        "as_of",
                        "earnings_date",
                        "revisions",
                        "surprise",
                        "reactions",
                    )
                }
                payload["summary"] = summary_lines(payload)
                return payload
        except Exception:
            pass
    payload = {
        "ticker": ticker,
        "as_of": datetime.now(timezone.utc).isoformat(),
        "earnings_date": (earnings_date or "")[:10] or None,
        "revisions": revisions(ticker),
        "surprise": surprise_history(ticker),
        "reactions": past_reactions(ticker),
    }
    payload["summary"] = summary_lines(payload)
    write_json(cache, payload)
    return payload


def summary_lines(payload: dict | None) -> list[str]:
    """Available revision and earnings-history measures as prose."""
    if not payload:
        return []
    lines: list[str] = []
    imp = payload.get("implied") or {}
    if imp.get("available"):
        basis = {
            "mid": "",
            "last_trade_only": " (no strike near spot quotes two-sided, so this is from last "
                               "traded prices and may be stale)",
        }.get(imp.get("quote_basis") or "", "")
        covers = "" if imp.get("expiry_covers_earnings", True) else " — expiry does NOT cover the print"
        lines.append(
            f"Options price a {imp['implied_move_pct']:.1f}% move by {imp.get('expiry')}"
            f"{covers}{basis}. That is the hurdle this thesis has to clear to pay."
        )
        if imp.get("quote_basis") != "mid":
            # Measured on a full run: only 3 of 190 chains had a quotable strike
            # near spot, because the fetch ran after the close. The implied move
            # is still the best available read, but it is a last trade, and the
            # spread half of the liquidity test cannot be evaluated at all.
            lines.append(
                "Note: fetched outside market hours, so almost no strike quotes two-sided and "
                "the move above comes from last traded prices. Re-check during the session."
            )
        if imp.get("open_interest_missing"):
            lines.append(
                "Options liquidity UNKNOWN: the data feed returned no open interest for this "
                f"chain ({imp.get('strikes')} strikes listed), which is a gap in the data rather "
                "than an empty market. Verify in your broker before sizing."
            )
        elif imp.get("thin") is True:
            spread = imp.get("spread_pct")
            detail = f", spread {spread:.0f}%" if spread is not None else ""
            lines.append(
                f"Chain is thin: {imp.get('open_interest')} contracts of open interest across "
                f"{imp.get('strikes')} strikes, {imp.get('two_sided_strikes')} of them "
                f"quotable{detail} — the position may be hard to put on at a sensible price."
            )
    elif imp.get("reason"):
        lines.append(f"No implied move available ({imp['reason']}).")
    rev = payload.get("revisions") or {}
    if rev.get("available"):
        d90, d30 = rev.get("change_90d_pct"), rev.get("change_30d_pct")
        parts = []
        if d90 is not None:
            parts.append(f"{d90:+.1f}% over 90 days")
        if d30 is not None:
            parts.append(f"{d30:+.1f}% over 30 days")
        if parts:
            lines.append(
                f"Consensus EPS for the current year has moved {' and '.join(parts)}."
            )
        up, down = rev.get("analysts_up_30d"), rev.get("analysts_down_30d")
        if up is not None and down is not None:
            lines.append(f"Analyst revisions in the last 30 days: {up} up, {down} down.")
    react = payload.get("reactions") or {}
    if react.get("available"):
        moves = ", ".join(f"{r['move_pct']:+.1f}%" for r in react["prints"])
        lines.append(
            f"Price reaction to the last {react['of']} reports, most recent first: {moves} "
            f"(average absolute move {react['avg_abs_move_pct']:.1f}%, "
            f"{react['down_prints']} of {react['of']} negative)."
        )
    sur = payload.get("surprise") or {}
    if sur.get("available"):
        lines.append(
            f"Beat consensus in {sur['beats']} of the last {sur['of']} quarters, "
            f"average surprise {sur['avg_surprise_pct']:+.1f}%."
        )
    return lines


def build_expectations(
    tickers: list[str], earnings_dates: dict[str, str] | None = None, force: bool = False
) -> dict[str, dict]:
    """Fetch for many names at once. Order of completion does not matter."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    if is_backdated():
        log("expectations: skipped, backdated run cannot see today's chains or revisions")
        return {}
    if not enabled():
        return {}
    dates = earnings_dates or {}
    workers = int(_cfg().get("workers") or 8)
    out: dict[str, dict] = {}
    log(f"expectations: {len(tickers)} tickers on {workers} workers")
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(expectations, t, dates.get(t), force): t for t in tickers
        }
        for done in as_completed(futures):
            ticker = futures[done]
            try:
                payload = done.result()
            except Exception as exc:
                log(f"expectations {ticker}: FAIL {exc}")
                continue
            if payload:
                out[ticker] = payload
    log(f"expectations: {len(out)}/{len(tickers)} resolved")
    return out
