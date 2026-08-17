from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

from ptm.config import env, set_roots, toml_settings
from ptm.io import write_df, write_json

FIXTURES = Path(__file__).parent / "fixtures"
PIPELINE = FIXTURES / "pipeline"


@pytest.fixture(autouse=True)
def isolate_roots(tmp_path, monkeypatch):
    data = tmp_path / "data"
    ideas = tmp_path / "ideas"
    data.mkdir()
    ideas.mkdir()
    set_roots(data=data, ideas=ideas)
    env.cache_clear()
    toml_settings.cache_clear()
    try:
        from ptm.ingest.edgar import ticker_map

        ticker_map.cache_clear()
    except Exception:
        pass
    yield {"data": data, "ideas": ideas, "tmp": tmp_path}
    set_roots(data=None, ideas=None)
    env.cache_clear()
    toml_settings.cache_clear()


def make_price_history(
    ticker: str,
    start: float = 100.0,
    drift: float = 0.15,
    days: int = 80,
    end: datetime | None = None,
) -> pd.DataFrame:
    end = end or datetime(2026, 8, 14, tzinfo=timezone.utc)
    rows = []
    price = start
    for i in range(days):
        day = end - timedelta(days=days - 1 - i)
        price = start + drift * (i / max(days - 1, 1))
        rows.append(
            {
                "date": day.strftime("%Y-%m-%d"),
                "open": price - 0.2,
                "high": price + 0.4,
                "low": price - 0.4,
                "close": price,
                "volume": 1_000_000,
                "ticker": ticker,
            }
        )
    return pd.DataFrame(rows)


def write_macro_inputs(
    *,
    spx_last: float | None = 5000.0,
    spx_high: float | None = 5200.0,
    tnx: float | None = 42.0,
    fvx: float | None = 40.0,
    irx: float | None = None,
    vix: float | None = 14.0,
    pmi: float | None = 55.0,
    new_orders: float | None = 56.0,
    nmi: float | None = 54.0,
    umcsi: float | None = 72.0,
    cpi_yoy: float | None = 0.03,
    m2_yoy: float | None = 0.05,
    skip_files: bool = False,
) -> None:
    from ptm.config import data_dir

    if skip_files:
        return
    curated = data_dir("curated")
    curated.mkdir(parents=True, exist_ok=True)
    spx_hist = []
    if spx_high is not None:
        spx_hist.append({"date": "2026-01-02", "close": spx_high})
    if spx_last is not None:
        spx_hist.append({"date": "2026-08-14", "close": spx_last})
    write_json(
        data_dir("curated", "macro_yfinance.json"),
        {
            "series": {
                "spx": {"last": spx_last, "history": spx_hist},
                "tnx": {"last": tnx, "history": []},
                "fvx": {"last": fvx, "history": []},
                "irx": {"last": irx, "history": []},
                "vix": {"last": vix, "history": []},
            }
        },
    )
    write_json(
        data_dir("curated", "macro_fred.json"),
        {
            "series": {
                "cpi": {"yoy": cpi_yoy, "last": 320.0},
                "umcsent": {"last": umcsi},
                "m2": {"yoy": m2_yoy, "last": 21000.0},
            }
        },
    )
    write_json(
        data_dir("curated", "ism.json"),
        {
            "pmi": pmi,
            "nmi": nmi,
            "manufacturing": {
                "headline": pmi,
                "report_month": "July 2026",
                "components": {"new_orders": {"value": new_orders}} if new_orders is not None else {},
                "industries": {"growth": [], "contraction": []},
                "new_orders_industries": {"growth": [], "contraction": []},
                "comments": [],
            },
            "services": {"headline": nmi, "industries": {"growth": [], "contraction": []}, "comments": []},
            "urls": {},
            "errors": [],
        },
    )


def seed_pipeline_data() -> None:
    from ptm.config import data_dir

    curated = data_dir("curated")
    curated.mkdir(parents=True, exist_ok=True)
    universe = pd.read_csv(PIPELINE / "universe.csv")
    fund = pd.read_csv(PIPELINE / "yahoo_fundamentals.csv")
    write_df(data_dir("curated", "universe.csv"), universe)
    write_df(data_dir("curated", "yahoo_fundamentals.csv"), fund)
    write_json(data_dir("curated", "sec_tickers.json"), {})
    ism = json.loads((PIPELINE / "ism.json").read_text(encoding="utf-8"))
    write_json(data_dir("curated", "ism.json"), ism)
    write_macro_inputs()
    frames = []
    for ticker in universe["ticker"].tolist():
        drift = 4.0 if ticker.startswith("L") or ticker == "M1" else -3.0
        frames.append(make_price_history(ticker, start=100.0, drift=drift))
    write_df(data_dir("curated", "prices.csv"), pd.concat(frames, ignore_index=True))
    write_json(
        data_dir("curated", "macro_yfinance.json"),
        json.loads((PIPELINE / "macro_yfinance.json").read_text(encoding="utf-8")),
    )
    write_json(
        data_dir("curated", "macro_fred.json"),
        json.loads((PIPELINE / "macro_fred.json").read_text(encoding="utf-8")),
    )
