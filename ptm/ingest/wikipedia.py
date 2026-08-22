from __future__ import annotations

import re
import time
from io import StringIO

import pandas as pd
import requests

from ptm.config import data_dir, toml_settings
from ptm.io import write_df
from ptm.log import log

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; PTM-Idea-Engine/0.1; research)",
    "Accept-Language": "en-US,en;q=0.9",
}

INDEX_LABELS = {"sp500": "S&P 500", "sp400": "S&P 400", "sp600": "S&P 600"}


def _clean_ticker(value: str) -> str:
    text = str(value).strip().upper().replace(".", "-")
    return re.sub(r"[^A-Z0-9-]", "", text)


def _pick_table(tables: list[pd.DataFrame]) -> pd.DataFrame:
    best = None
    best_rows = 0
    for table in tables:
        cols = [str(c).lower() for c in table.columns]
        joined = " ".join(cols)
        if any(key in joined for key in ("symbol", "ticker")):
            if len(table) > best_rows:
                best = table
                best_rows = len(table)
    if best is None:
        raise RuntimeError("No constituent table found")
    return best


def _normalize(frame: pd.DataFrame, index_key: str) -> pd.DataFrame:
    rename = {}
    for col in frame.columns:
        low = str(col).lower()
        if "symbol" in low or low == "ticker":
            rename[col] = "ticker"
        elif low in {"security", "company", "name"} or "company" in low:
            rename[col] = "name"
        elif "gics sector" in low or low == "sector":
            rename[col] = "sector"
        elif "gics sub" in low or "industry" in low:
            rename[col] = "industry"
    out = frame.rename(columns=rename)
    for required in ("ticker", "name"):
        if required not in out.columns:
            raise RuntimeError(f"Missing {required} in Wikipedia table for {index_key}")
    if "sector" not in out.columns:
        out["sector"] = ""
    if "industry" not in out.columns:
        out["industry"] = ""
    out["ticker"] = out["ticker"].map(_clean_ticker)
    out = out[out["ticker"].str.len() > 0]
    out["index"] = index_key
    return out[["ticker", "name", "sector", "industry", "index"]].drop_duplicates("ticker")


def fetch_index(index_key: str) -> pd.DataFrame:
    url = toml_settings()["universe"]["wikipedia"][index_key]
    log(f"universe: fetching {INDEX_LABELS.get(index_key, index_key)} {url}")
    response = requests.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    tables = pd.read_html(StringIO(response.text))
    frame = _normalize(_pick_table(tables), index_key)
    log(f"universe: {index_key} {len(frame)} tickers")
    return frame


def build_universe() -> pd.DataFrame:
    frames = []
    for key in toml_settings()["universe"]["indices"]:
        frame = fetch_index(key)
        frames.append(frame)
        time.sleep(1.2)
    combined = pd.concat(frames, ignore_index=True)
    grouped = (
        combined.groupby("ticker", as_index=False)
        .agg(
            name=("name", "first"),
            sector=("sector", "first"),
            industry=("industry", "first"),
            indices=("index", lambda s: ",".join(sorted(set(s)))),
        )
    )
    path = data_dir("curated", "universe.csv")
    write_df(path, grouped)
    log(f"universe: wrote {len(grouped)} unique tickers")
    return grouped
