"""FRED fallback for macro series yfinance cannot supply."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import requests

from ptm.asof import as_of_date, is_backdated
from ptm.config import data_dir, env, toml_settings
from ptm.io import write_json
from ptm.log import log

FRED_OBS = "https://api.stlouisfed.org/fred/series/observations"


def _truncate(rows: list[dict], lag_days: int = 0) -> list[dict]:
    """Drop observations the run date could not have seen.

    `lag_days` backs the cutoff off by a publication lag; pass 0 when FRED has
    already returned a true vintage.
    """
    if not is_backdated():
        return rows
    cutoff = (as_of_date() - timedelta(days=lag_days)).isoformat()
    return [row for row in rows if str(row.get("date", ""))[:10] <= cutoff]


def _publication_lag_days() -> int:
    """How long after a period ends before its print is public.

    Only used on the keyless CSV path, which has no vintage support. Monthly US
    macro (CPI, payrolls, IP, M2) lands two to six weeks after month end, so a
    45-day haircut is conservative without gutting the series.
    """
    cfg = toml_settings().get("fred_asof") or {}
    return int(cfg.get("publication_lag_days") or 45)


def fetch_series(series_id: str) -> list[dict]:
    params = {
        "series_id": series_id,
        "file_type": "json",
        "sort_order": "desc",
        "limit": 240 if is_backdated() else 24,
    }
    if is_backdated():
        cutoff = as_of_date().isoformat()
        params["observation_end"] = cutoff
        # observation_end alone is not enough: it bounds the period a number
        # DESCRIBES, not when it was released. July CPI is stamped 2026-07-01
        # but only published in mid-August. realtime_start/end ask FRED for the
        # vintage as it stood on the run date, which fixes both the release lag
        # and later revisions.
        params["realtime_start"] = cutoff
        params["realtime_end"] = cutoff
    key = env().fred_api_key
    if key:
        params["api_key"] = key
        response = requests.get(FRED_OBS, params=params, timeout=30)
        if response.status_code < 400:
            observations = response.json().get("observations", [])
            out = []
            for item in observations:
                if item.get("value") in {".", "", None}:
                    continue
                out.append({"date": item["date"], "value": float(item["value"])})
            return _truncate(list(reversed(out)))[-24:]
        log(f"fred {series_id}: vintage request HTTP {response.status_code}; falling back to CSV")
    csv_url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    response = requests.get(csv_url, timeout=30)
    if response.status_code >= 400:
        return []
    lines = [line.strip() for line in response.text.splitlines() if line.strip()]
    out = []
    for line in lines[1:]:
        parts = line.split(",")
        if len(parts) < 2 or parts[1] in {".", ""}:
            continue
        try:
            out.append({"date": parts[0], "value": float(parts[1])})
        except ValueError:
            continue
    return _truncate(out, lag_days=_publication_lag_days())[-24:]


def fetch_fred_macro() -> dict:
    cfg = toml_settings()["fred"]
    series = {}
    log(f"fred: {len(cfg)} series")
    for name, series_id in cfg.items():
        log(f"fred {name}={series_id}")
        values = fetch_series(series_id)
        last = values[-1]["value"] if values else None
        yoy = None
        if len(values) >= 13:
            prev = values[-13]["value"]
            if prev:
                yoy = last / prev - 1.0
        series[name] = {"id": series_id, "last": last, "yoy": yoy, "history": values[-24:]}
        log(f"fred {name} last={last} points={len(values)}")
    payload = {"as_of": datetime.now(timezone.utc).isoformat(), "series": series}
    write_json(data_dir("curated", "macro_fred.json"), payload)
    log("fred done")
    return payload
