from __future__ import annotations

import time
from datetime import datetime, timezone

import pandas as pd
import yfinance as yf

from ptm.config import data_dir, toml_settings
from ptm.io import read_df, write_df, write_json
from ptm.log import elapsed_since, eta, log
from ptm.timing_prm import normalize_earnings_date


def _last_close(ticker: str, period: str = "5y") -> pd.Series:
    hist = yf.Ticker(ticker).history(period=period, auto_adjust=True)
    if hist.empty:
        return pd.Series(dtype=float)
    return hist["Close"].dropna()


def _merge_fundamentals_csv(frame: pd.DataFrame) -> None:
    path = data_dir("curated", "yahoo_fundamentals.csv")
    if path.exists() and not frame.empty:
        try:
            old = read_df(path)
            if not old.empty:
                frame = pd.concat([old, frame], ignore_index=True)
        except Exception as exc:
            log(f"fundamentals checkpoint: could not read cache ({exc}); writing fetched rows only")
    if frame.empty:
        return
    write_df(path, frame.drop_duplicates(subset=["ticker"], keep="last"))


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
    log(f"prices: {len(unique)} tickers in {len(chunks)} chunks of 80 ({period})")
    for i, chunk in enumerate(chunks, start=1):
        lo = (i - 1) * 80 + 1
        hi = min(i * 80, len(unique))
        log(f"prices chunk {i}/{len(chunks)} tickers {lo}-{hi} ({chunk[0]}…{chunk[-1]})")
        try:
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


def fetch_fundamentals(tickers: list[str], *, persist: bool = True) -> pd.DataFrame:
    records = []
    unique = [t for t in dict.fromkeys(tickers) if t]
    if not unique:
        return pd.DataFrame()
    started = time.monotonic()
    log(f"fundamentals: fetching {len(unique)} tickers from Yahoo (slow; one info call each)")
    for i, ticker in enumerate(unique, start=1):
        info = {}
        status = "ok"
        try:
            stock = yf.Ticker(ticker)
            info = stock.info or {}
            cal = {}
            try:
                cal = stock.calendar or {}
            except Exception as exc:
                cal = {}
                status = f"calendar {exc}"
        except Exception as exc:
            info, cal = {}, {}
            status = f"FAIL {exc}"
        earnings_date = None
        if isinstance(cal, dict):
            raw = cal.get("Earnings Date") or cal.get("earningsDate")
            earnings_date = normalize_earnings_date(raw)
        elif hasattr(cal, "to_dict"):
            earnings_date = normalize_earnings_date(cal.to_dict())
        name = info.get("shortName") or info.get("longName") or ticker
        pe = info.get("forwardPE")
        if not info:
            status = status if status.startswith("FAIL") else "empty"
        records.append(
            {
                "ticker": ticker,
                "name": name,
                "sector": info.get("sector") or "",
                "industry": info.get("industry") or "",
                "price": info.get("currentPrice") or info.get("regularMarketPrice"),
                "market_cap": info.get("marketCap"),
                "forward_eps": info.get("forwardEps"),
                "trailing_eps": info.get("trailingEps"),
                "forward_pe": pe,
                "trailing_pe": info.get("trailingPE"),
                "earnings_growth": info.get("earningsGrowth"),
                "revenue_growth": info.get("revenueGrowth"),
                "target_mean": info.get("targetMeanPrice"),
                "recommendation": info.get("recommendationMean"),
                "shares": info.get("sharesOutstanding"),
                "earnings_date": earnings_date,
                "beta": info.get("beta"),
            }
        )
        log(
            f"fundamentals {i}/{len(unique)} {ticker}  {status}  "
            f"pe={pe}  elapsed {elapsed_since(started)}  eta {eta(i, len(unique), started)}"
        )
        if i % 25 == 0 or i == len(unique):
            _merge_fundamentals_csv(pd.DataFrame(records))
            log(f"fundamentals checkpoint {i}/{len(unique)} written")
        time.sleep(0.05)
    frame = pd.DataFrame(records)
    if persist:
        _merge_fundamentals_csv(frame)
    log(f"fundamentals done: {len(frame)} rows in {elapsed_since(started)}")
    return frame
