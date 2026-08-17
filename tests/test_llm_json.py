import json
from datetime import datetime, timedelta, timezone

import pytest

from ptm.llm import _extract_json, filter_non_earnings, sanitize_kpis


def test_extract_plain_object():
    assert _extract_json('{"markdown": "ok"}') == {"markdown": "ok"}


def test_extract_markdown_fence():
    blob = "```json\n{\"markdown\": \"# LONG X\"}\n```"
    assert _extract_json(blob)["markdown"] == "# LONG X"


def test_extract_trailing_junk():
    blob = '{"markdown": "ok"}\nHere is extra prose'
    assert _extract_json(blob)["markdown"] == "ok"


def test_extract_control_characters():
    blob = '{"markdown": "line1\x00line2"}'
    payload = _extract_json(blob)
    assert "line1" in payload["markdown"]


def test_extract_first_object_when_two_present():
    blob = '{"a": 1}\n{"b": 2}'
    assert _extract_json(blob) == {"a": 1}


def test_extract_no_object_raises():
    with pytest.raises(json.JSONDecodeError):
        _extract_json("not json at all")


def test_filter_non_earnings_keeps_dated_events():
    dated = (datetime.now(timezone.utc) + timedelta(days=30)).strftime("%Y-%m-%d")
    kept = filter_non_earnings(
        [
            "Has Arcosa Outpaced Other Construction Stocks This Year?",
            {"event": "Investor day", "date": dated, "why": "guidance update"},
            "Loss ratio 55.1 % 53.1 % 2.0 | Combined ratio dump",
            "Undated rumor with no calendar",
        ]
    )
    assert any("Investor day" in item for item in kept)
    assert not any("Outpaced" in item for item in kept)
    assert not any("Combined" in item for item in kept)


def test_sanitize_kpis_drops_statement_lines():
    cleaned, stripped = sanitize_kpis(["revenue", "backlog", "net_income", "utilization"])
    assert cleaned == ["backlog", "utilization"]
    assert stripped is True
