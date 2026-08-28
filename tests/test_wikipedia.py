from __future__ import annotations

import pandas as pd
import pytest

from ptm.ingest.wikipedia import _normalize, _pick_table


def _constituents(n: int = 2) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Symbol": [f"T{i}" for i in range(n)],
            "Security": [f"Name {i}" for i in range(n)],
            "GICS Sector": ["Materials"] * n,
            "GICS Sub-Industry": ["Aluminum"] * n,
        }
    )


def _changes(n: int = 10) -> pd.DataFrame:
    return pd.DataFrame(
        {
            ("Date", ""): [f"2026-01-{i:02d}" for i in range(1, n + 1)],
            ("Added", "Ticker"): [f"A{i}" for i in range(n)],
            ("Added", "Security"): [f"Added {i}" for i in range(n)],
            ("Removed", "Ticker"): [f"R{i}" for i in range(n)],
            ("Removed", "Security"): [f"Removed {i}" for i in range(n)],
            ("Reason", ""): ["Market capitalization change."] * n,
        }
    )


def test_pick_table_skips_longer_additions_removals_history():
    constituents = _constituents(2)
    picked = _pick_table([_changes(10), constituents])
    assert list(picked["Symbol"]) == ["T0", "T1"]


def test_pick_table_raises_when_only_changes_table_exists():
    with pytest.raises(RuntimeError, match="No constituent table found"):
        _pick_table([_changes(10)])


def test_normalize_symbol_gics_table():
    out = _normalize(_constituents(1), "sp400")
    row = out.iloc[0]
    assert row["ticker"] == "T0"
    assert row["name"] == "Name 0"
    assert row["sector"] == "Materials"
    assert row["industry"] == "Aluminum"
    assert row["index"] == "sp400"
