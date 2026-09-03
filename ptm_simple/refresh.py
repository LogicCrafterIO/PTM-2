"""Fetch fundamentals for the simple process's universe — separately.

Normally the simple process just reads the cached fundamentals table the main
pipeline built (data/curated/yahoo_fundamentals.csv). This module gives it its
own fetch path so the quant table can be as fresh as the run date without
re-running the main pipeline:

1. prices: batched yfinance download for the target tickers -> prices.csv
   (the EDGAR rows are priced at the run date's close, so prices first)
2. EDGAR rows: ptm.fundamentals.build_fundamentals — one XBRL pull per ticker
   at the run date (cached rows are only reused when their as_of matches the
   run date, so a new run date means a fresh pull by design)
3. consensus: analyst forward EPS comes from data/raw/estimates caches with
   their own freshness window; --estimates deletes them for a forced re-pull
4. rebuild the quant table from the saved radar (no LLM calls anywhere in this
   flow; the prose that reads these numbers is re-rendered by whichever pass
   owns it — coverage, group review, or the ranking process's rankings)

Both qualitative layers read the table this writes: ptm_simple's flag review
and ptm_setups' group ranking.
"""

from __future__ import annotations

import json
import time
from datetime import date

from ptm.log import elapsed_since, log


def simple_universe(theme_map: dict, radar: dict | None = None, non_cold_only: bool = True):
    """{ticker, name, sector, industry} rows for the fetch universe.

    non_cold_only narrows to the members of non-COLD themes — exactly what the
    quant table covers; without it, every member of the theme map. Meta comes
    from the cached fundamentals table when the ticker is already there."""
    import pandas as pd

    from ptm_simple.run import _fundamentals

    fund = _fundamentals()
    tickers: list[str] = []
    if non_cold_only and radar:
        for row in radar.get("themes", []):
            if row.get("status") == "COLD":
                continue
            for m in radar.get("members", {}).get(row["theme"], []) or []:
                t = m.get("ticker") if isinstance(m, dict) else str(m)
                if t and t not in tickers:
                    tickers.append(t)
    else:
        for entry in theme_map.get("themes", []):
            for m in entry.get("members", []) or []:
                t = m.get("ticker") if isinstance(m, dict) else str(m)
                if t and t not in tickers:
                    tickers.append(t)
    rows = []
    for t in tickers:
        f = fund.get(t) or {}
        rows.append(
            {
                "ticker": t,
                "name": str(f.get("name") or ""),
                "sector": str(f.get("sector") or ""),
                "industry": str(f.get("industry") or ""),
            }
        )
    return pd.DataFrame(rows)


def _rebuild_quant(ref: date) -> dict:
    """Rebuild the quant table from the saved radar.

    Report re-rendering used to happen here too, off the simple book — but the
    book was removed when trade ideas replaced it, taking `write_idea_reports`
    with it and leaving this function raising ImportError on every call. Reports
    now belong to the passes that own them (analyze-all writes the coverage
    reports, the group review its own markdown, the ranking pass its rankings),
    so a fundamentals refresh rebuilds the numbers and stops there — rerun the
    owning pass to re-render its prose against them. `reports` stays in the
    result for the CLI and the viewer, always 0.
    """
    from ptm_simple import simple_dir
    from ptm_simple.quant import build_quant

    out = {"quant_rows": 0, "reports": 0}
    radar_path = simple_dir(f"radar_{ref.isoformat()}.json")
    if radar_path.exists():
        radar = json.loads(radar_path.read_text(encoding="utf-8"))
        non_cold = [r for r in radar.get("themes", []) if r.get("status") != "COLD"]
        payload = build_quant(ref, non_cold, radar.get("members"))
        out["quant_rows"] = len(payload["rows"])
    return out


def refresh_fundamentals(
    source: str = "wiki",
    ref: date | None = None,
    non_cold_only: bool = True,
    force: bool = False,
    with_estimates: bool = False,
    with_prices: bool = True,
) -> dict:
    """Fresh fundamentals for the simple universe at the run date.

    Network-bound (yfinance + SEC EDGAR); everything else is local. Returns a
    summary dict for the CLI/viewer to display."""
    from ptm.asof import as_of_date
    from ptm.config import data_dir
    from ptm_simple.run import load_theme_map

    ref = ref or as_of_date()
    started = time.monotonic()
    theme_map = load_theme_map(source)
    from ptm_simple import simple_dir

    radar_path = simple_dir(f"radar_{ref.isoformat()}.json")
    radar = None
    if radar_path.exists():
        radar = json.loads(radar_path.read_text(encoding="utf-8"))
    if non_cold_only and radar is None:
        raise SystemExit(f"no radar for {ref.isoformat()} — run the radar first, or pass the full map")
    universe = simple_universe(theme_map, radar, non_cold_only)
    tickers = [t for t in universe["ticker"].tolist() if t]
    log(f"refresh: {len(tickers)} ticker(s) for map '{source}' "
        f"({'non-COLD themes' if non_cold_only else 'whole map'}) at {ref.isoformat()}")

    if with_estimates and tickers:
        est_dir = data_dir("raw", "estimates")
        removed = 0
        for t in tickers:
            p = est_dir / f"{t}.json"
            if p.exists():
                p.unlink()
                removed += 1
        log(f"refresh: cleared {removed} consensus cache(s) for a fresh forward-EPS pull")

    prices_ok = None
    if with_prices and tickers:
        # yfinance keeps SQLite caches (tz/cookie/ISIN) under the user profile
        # by default; redirect them into data/raw so the sandboxed run can
        # actually create them.
        from ptm.config import data_dir as _data_dir

        cache_dir = _data_dir("raw", "yfinance_cache")
        try:
            import yfinance as _yf

            cache_dir.mkdir(parents=True, exist_ok=True)
            _yf.set_tz_cache_location(str(cache_dir))
        except Exception as exc:
            log(f"refresh: yfinance cache redirect failed ({exc})")
        from ptm.ingest.yfinance_data import fetch_prices

        price_frame = fetch_prices(tickers)
        prices_ok = bool(price_frame is not None and not price_frame.empty)
        if not prices_ok:
            log("refresh: price download failed — EDGAR rows will be priced at the last cached close")

    from ptm.fundamentals import build_fundamentals

    frame = build_fundamentals(universe, upto=ref, force=force)
    fetched = int(frame["ticker"].nunique()) if not frame.empty else 0

    summary = _rebuild_quant(ref)
    result = {
        "ref": ref.isoformat(),
        "universe": len(tickers),
        "fundamentals_rows": fetched,
        "prices_refreshed": prices_ok,
        **summary,
        "elapsed_s": round(time.monotonic() - started, 1),
    }
    log(f"refresh done: {result['fundamentals_rows']} rows at {ref.isoformat()} "
        f"quant {result['quant_rows']} reports {result['reports']} in {result['elapsed_s']}s")
    return result