"""Weekly theme radar: which themes are activating, without any price input.

Signals per theme, all measured (docs/simple_idea_process.md §2 stage 1):
- revision breadth: share of members with FY1 EPS estimates up/down over 90d
  (PTM's expectations cache, aggregated to the cluster)
- print density: members with a dated earnings print in the next 14 days,
  and the cluster bellwether (largest market cap printing)
- divergence: members revising against their own theme (the short list)

The theme news call (--llm) grades WHY-NOW activation per theme; without it
the radar is fully deterministic. Statuses: ACTIVE / WARM / COLD with a
long/short lean from the breadth sign.
"""

from __future__ import annotations

import json
import time
from datetime import date, timedelta
from pathlib import Path

from ptm.log import log
from ptm_simple import simple_dir

_MAX_AGE_DAYS = 7  # a radar reading older than a week is stale for gating


def _exp_cache(ticker: str):
    from ptm.config import data_dir

    return data_dir("raw", "expectations", f"{ticker}.json")


def _fundamentals() -> dict[str, dict]:
    import pandas as pd

    path = Path("data/curated/yahoo_fundamentals.csv")
    if not path.exists():
        return {}
    df = pd.read_csv(path).set_index("ticker")
    return {t: row for t, row in df.to_dict(orient="index").items()}


def _member_snapshot(ticker: str, fund: dict, ref: date) -> dict:
    """Measured inputs for one member; `covered` False when expectations are missing/stale."""
    out = {
        "ticker": ticker,
        "covered": False,
        "rev90": None,
        "up30": None,
        "down30": None,
        "earnings_date": None,
        "days_to_print": None,
        "revenue": None,
        "net_income": None,
        "cash": None,
        "market_cap": None,
    }
    row = fund.get(ticker) or {}
    for key in ("revenue", "net_income", "cash", "market_cap"):
        val = row.get(key)
        if val is not None and val == val:
            out[key] = float(val)
    cache = _exp_cache(ticker)
    if cache.exists():
        age_days = (time.time() - cache.stat().st_mtime) / 86400.0
        if age_days <= _MAX_AGE_DAYS * 5:  # cache tolerant: the weekly radar refills it
            try:
                exp = json.loads(cache.read_text(encoding="utf-8"))
            except Exception:
                exp = None
            if exp:
                rev = exp.get("revisions") or {}
                if rev.get("available"):
                    out["covered"] = True
                    out["rev90"] = rev.get("change_90d_pct")
                    out["up30"] = rev.get("analysts_up_30d")
                    out["down30"] = rev.get("analysts_down_30d")
                ed = exp.get("earnings_date")
                if ed:
                    out["earnings_date"] = ed
                    try:
                        out["days_to_print"] = (date.fromisoformat(str(ed)[:10]) - ref).days
                    except ValueError:
                        pass
    return out


def theme_radar(theme_entry: dict, fund: dict, ref: date) -> dict:
    built = [
        m if isinstance(m, dict) else _member_snapshot(m, fund, ref)
        for m in theme_entry["members"]
    ]
    members = built
    covered = [m for m in members if m["covered"]]
    breadth = 0.0
    if covered:
        up = sum(1 for m in covered if (m["rev90"] or 0) > 0.5)
        down = sum(1 for m in covered if (m["rev90"] or 0) < -0.5)
        breadth = (up - down) / len(covered)
    prints = sorted(
        [m for m in members if m["days_to_print"] is not None and -1 <= m["days_to_print"] <= 14],
        key=lambda m: -(m["market_cap"] or 0),
    )
    bellwether = prints[0]["ticker"] if prints else None
    coverage = len(covered) / len(members) if members else 0.0
    lean = "long" if breadth > 0 else "short" if breadth < 0 else "flat"
    if coverage >= 0.4 and abs(breadth) >= 0.4:
        status = "ACTIVE"
    elif coverage >= 0.4 and abs(breadth) >= 0.2:
        status = "WARM"
    else:
        status = "COLD"
    return {
        "theme": theme_entry["theme"],
        "thesis": theme_entry.get("thesis", ""),
        "status": status,
        "lean": lean,
        "breadth": round(breadth, 3),
        "coverage": round(coverage, 2),
        "members_covered": len(covered),
        "members_total": len(members),
        "prints_14d": [
            {"ticker": m["ticker"], "days_to_print": m["days_to_print"], "earnings_date": m["earnings_date"]}
            for m in prints
        ][:6],
        "bellwether": bellwether,
        "divergent": [m["ticker"] for m in covered if (m["rev90"] or 0) * breadth < 0],
        "members": members,
        "why_now": None,  # filled by the LLM activation call when enabled
    }


def run_radar(theme_map: dict, ref: date, refresh: int = 0) -> list[dict]:
    """Radar rows for every theme; optionally refresh N member expectation caches per theme."""
    fund = _fundamentals()
    rows = []
    for entry in theme_map["themes"]:
        if refresh > 0:
            _refresh_members(entry["members"][:refresh])
        rows.append(theme_radar(entry, fund, ref))
    active = sum(1 for r in rows if r["status"] == "ACTIVE")
    warm = sum(1 for r in rows if r["status"] == "WARM")
    log(f"radar: {active} ACTIVE / {warm} WARM / {len(rows) - active - warm} COLD of {len(rows)} themes")
    return rows


def _refresh_members(tickers: list[str]) -> None:
    from ptm.ingest.expectations import enabled, expectations

    if not enabled():
        return
    for ticker in tickers:
        try:
            expectations(ticker, force=True)
        except Exception as exc:  # a dead feed must not kill the radar
            log(f"expectations refresh failed for {ticker}: {exc}")


def write_radar(rows: list[dict], ref: date, theme_map: dict | None = None) -> Path:
    from ptm.io import write_json
    from ptm_simple import simple_dir

    payload = {
        "as_of": ref.isoformat(),
        "generated_at": time.time(),
        # which theme map produced these rows — manual and wiki maps share the
        # radar_<date>.json file, so the artifact must say which it is
        "map_source": (theme_map or {}).get("source", ""),
        "themes": [{k: v for k, v in row.items() if k != "members"} for row in rows],
        "members": {row["theme"]: row["members"] for row in rows},
    }
    path = simple_dir(f"radar_{ref.isoformat()}.json")
    write_json(path, payload)
    log(f"radar written -> {path}")
    return path