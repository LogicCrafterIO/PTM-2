"""Price history from Yahoo. Prices only.

Fundamentals used to come from Yahoo's `info` snapshot; they now come from SEC
filings (ptm/fundamentals.py). Nothing in this module may return a fundamental
value, an analyst estimate, or an earnings calendar.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import pandas as pd
import yfinance as yf

from ptm.asof import as_of_date, is_backdated
from ptm.config import data_dir, toml_settings
from ptm.io import write_df, write_json
from ptm.log import elapsed_since, eta, log


def _end_bound() -> str | None:
    """yfinance `end` is exclusive; pass the day after the run date so the
    run date's own close is included, and None when not backdating."""
    if not is_backdated():
        return None
    return (as_of_date() + timedelta(days=1)).isoformat()


def _last_close(ticker: str, period: str = "5y") -> pd.Series:
    end = _end_bound()
    if end:
        start = (as_of_date() - timedelta(days=5 * 366)).isoformat()
        hist = yf.Ticker(ticker).history(start=start, end=end, auto_adjust=True)
    else:
        hist = yf.Ticker(ticker).history(period=period, auto_adjust=True)
    if hist.empty:
        return pd.Series(dtype=float)
    return hist["Close"].dropna()


def fetch_macro_prices() -> dict:
    cfg = toml_settings()["yfinance"]
    series = {}
    started = time.monotonic()
    items = list(cfg.items())
    log(f"macro prices: {len(items)} symbols")
    for i, (key, symbol) in enumerate(items, start=1):
        log(f"macro prices {i}/{len(items)} {key}={symbol}")
        try:
            closes = _last_close(symbol)
            last = None if closes.empty else float(closes.iloc[-1])
            series[key] = {
                "symbol": symbol,
                "last": last,
                "history": [] if closes.empty else [
                    {"date": idx.strftime("%Y-%m-%d"), "close": float(val)}
                    for idx, val in closes.tail(800).items()
                ],
            }
            log(f"macro prices {i}/{len(items)} {symbol} last={last}")
        except Exception as exc:
            series[key] = {"symbol": symbol, "last": None, "history": [], "error": str(exc)}
            log(f"macro prices {i}/{len(items)} {symbol} FAIL {exc}")
        time.sleep(0.15)
    path = data_dir("curated", "macro_yfinance.json")
    write_json(path, {"as_of": datetime.now(timezone.utc).isoformat(), "series": series})
    log(f"macro prices done in {elapsed_since(started)}")
    return series


def fetch_prices(tickers: list[str], period: str = "1y") -> pd.DataFrame:
    unique = [t for t in dict.fromkeys(tickers) if t]
    chunks = [unique[i : i + 80] for i in range(0, len(unique), 80)]
    rows = []
    started = time.monotonic()
    end_bound = _end_bound()
    start_bound = None
    if end_bound:
        years = 2 if period.endswith("y") and period[:-1].isdigit() and int(period[:-1]) > 1 else 1
        start_bound = (as_of_date() - timedelta(days=int(365.25 * years) + 10)).isoformat()
        log(f"prices: backdated window {start_bound} .. {end_bound} (exclusive end)")
    log(f"prices: {len(unique)} tickers in {len(chunks)} chunks of 80 ({period})")
    for i, chunk in enumerate(chunks, start=1):
        lo = (i - 1) * 80 + 1
        hi = min(i * 80, len(unique))
        log(f"prices chunk {i}/{len(chunks)} tickers {lo}-{hi} ({chunk[0]}…{chunk[-1]})")
        try:
            if end_bound:
                hist = yf.download(
                    chunk,
                    start=start_bound,
                    end=end_bound,
                    group_by="ticker",
                    auto_adjust=True,
                    threads=True,
                    progress=False,
                )
            else:
                hist = yf.download(
                    chunk,
                    period=period,
                    group_by="ticker",
                    auto_adjust=True,
                    threads=True,
                    progress=False,
                )
        except Exception as exc:
            log(f"prices chunk {i}/{len(chunks)} FAIL {exc}")
            time.sleep(0.4)
            continue
        if hist.empty:
            log(f"prices chunk {i}/{len(chunks)} empty")
            time.sleep(0.4)
            continue
        got = 0
        if len(chunk) == 1:
            ticker = chunk[0]
            frame = hist.reset_index()
            frame["ticker"] = ticker
            rows.append(frame)
            got = 1
        else:
            for ticker in chunk:
                try:
                    sub = hist[ticker].dropna(how="all").reset_index()
                except Exception:
                    continue
                if sub.empty:
                    continue
                sub["ticker"] = ticker
                rows.append(sub)
                got += 1
        log(
            f"prices chunk {i}/{len(chunks)} got {got}/{len(chunk)}  "
            f"elapsed {elapsed_since(started)}  eta {eta(i, len(chunks), started)}"
        )
        time.sleep(0.4)
    if not rows:
        log("prices: no rows downloaded")
        return pd.DataFrame()
    out = pd.concat(rows, ignore_index=True)
    write_df(data_dir("curated", "prices.csv"), out)
    log(f"prices done: {out['ticker'].nunique()} tickers, {len(out)} bars in {elapsed_since(started)}")
    return out
