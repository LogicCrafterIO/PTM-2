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


def _col_text(col: object) -> str:
    """Flatten a pandas column label (including MultiIndex tuples) to lowercase text."""
    if isinstance(col, tuple):
        parts = [
            str(part).strip()
            for part in col
            if str(part).strip() and not str(part).startswith("Unnamed")
        ]
        return " ".join(parts).lower()
    return str(col).strip().lower()


def _pick_table(tables: list[pd.DataFrame]) -> pd.DataFrame:
    """Prefer the constituent list over a longer Added/Removed history table."""
    scored: list[tuple[int, pd.DataFrame]] = []
    for table in tables:
        texts = [_col_text(col) for col in table.columns]
        joined = " ".join(texts)
        if not any("symbol" in text or "ticker" in text for text in texts):
            continue
        if "added" in joined and "removed" in joined:
            continue
        score = len(table)
        if any("gics" in text or text == "sector" for text in texts):
            score += 10_000
        if any(
            text in {"security", "company", "name"} or "company" in text or "security" in text
            for text in texts
        ):
            score += 1_000
        scored.append((score, table))
    if not scored:
        raise RuntimeError("No constituent table found")
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[0][1]


def _normalize(frame: pd.DataFrame, index_key: str) -> pd.DataFrame:
    rename = {}
    used: set[str] = set()
    for col in frame.columns:
        low = _col_text(col)
        if "ticker" not in used and ("symbol" in low or "ticker" in low):
            rename[col] = "ticker"
            used.add("ticker")
        elif "name" not in used and (
            low in {"security", "company", "name"} or "company" in low or "security" in low
        ):
            rename[col] = "name"
            used.add("name")
        elif "sector" not in used and ("gics sector" in low or low == "sector"):
            rename[col] = "sector"
            used.add("sector")
        elif "industry" not in used and ("gics sub" in low or "industry" in low):
            rename[col] = "industry"
            used.add("industry")
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
