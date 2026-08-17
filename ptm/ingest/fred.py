"""FRED fallback for macro series yfinance cannot supply."""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import requests

from ptm.config import data_dir, env, toml_settings
from ptm.io import write_json
from ptm.log import log

FRED_OBS = "https://api.stlouisfed.org/fred/series/observations"


def fetch_series(series_id: str) -> list[dict]:
    params = {
        "series_id": series_id,
        "file_type": "json",
        "sort_order": "desc",
        "limit": 24,
    }
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
            return list(reversed(out))
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
    return out[-24:]


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
