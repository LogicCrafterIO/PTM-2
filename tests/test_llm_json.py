import json
from datetime import datetime, timedelta, timezone

import pytest

from ptm.llm import _extract_json, filter_non_earnings, qualitative, sanitize_kpis
from ptm.models import Candidate, Side


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


def test_qualitative_two_pass_uses_verdict_why(monkeypatch):
    monkeypatch.setattr("ptm.llm.llm_available", lambda: True)
    calls: list[str] = []

    def fake_chat(system: str, user: str, **kwargs):
        calls.append(system)
        if "Extract operating facts" in system:
            return {
                "business_in_one_line": "Makes HVAC equipment",
                "operating_plan": "Grow data-center backlog",
                "kpis": ["backlog", "revenue"],
                "red_flags": [],
                "ism_link": "Machinery growth",
                "quotes": ["backlog rose to a record"],
            }
        return {
            "supports_outlier": True,
            "why": "Backlog growth supports paying a premium for acceleration.",
            "denial_reason": "",
        }

    monkeypatch.setattr("ptm.llm.chat_json", fake_chat)
    result = qualitative(
        Candidate(ticker="X", side=Side.LONG, eg_case="long_case_1_acceleration", pe1=30, sector_pe1=20),
        "BUSINESS: HVAC for data centers. Backlog rose to a record.",
    )
    assert len(calls) == 2
    assert result.supports_outlier is True
    assert "premium" in result.why.lower()
    assert "backlog" in [k.lower() for k in result.kpis]
    assert "generic_kpis_stripped" in result.red_flags


def test_qualitative_json_fail_both_passes_is_null(monkeypatch):
    monkeypatch.setattr("ptm.llm.llm_available", lambda: True)

    def boom(system: str, user: str, **kwargs):
        raise json.JSONDecodeError("Unterminated string", "{", 0)

    monkeypatch.setattr("ptm.llm.chat_json", boom)
    result = qualitative(Candidate(ticker="PFE", side=Side.SHORT), "BUSINESS: Pfizer sells medicines.")
    assert result.supports_outlier is None
    assert "llm_json_failed" in result.red_flags


def test_qualitative_verdict_json_fail_returns_bool(monkeypatch):
    monkeypatch.setattr("ptm.llm.llm_available", lambda: True)

    def fake_chat(system: str, user: str, **kwargs):
        if "Extract operating facts" in system:
            return {"business_in_one_line": "Pays claims", "operating_plan": "Cut costs", "kpis": ["loss ratio"], "red_flags": []}
        raise json.JSONDecodeError("Unterminated string", "{", 0)

    monkeypatch.setattr("ptm.llm.chat_json", fake_chat)
    result = qualitative(Candidate(ticker="PFE", side=Side.SHORT, eg_case="short_non_ideal"), "BUSINESS: insurer")
    assert result.supports_outlier is False
    assert "llm_json_failed_verdict" in result.red_flags


def test_trailing_commas_are_repaired():
    """The most common small-model syntax error must not cost an idea its
    catalysts; observed at ~2% of calls across a 308-name run."""
    from ptm.llm import _extract_json

    got = _extract_json('{"non_earnings": ["a", "b",], "meaningful": true,}')
    assert got["non_earnings"] == ["a", "b"]
    assert got["meaningful"] is True

    fenced = '```json\n{"a": [1, 2,],}\n```'
    assert _extract_json(fenced)["a"] == [1, 2]

    prefixed = 'Here you go: {"x": {"y": [1,],},} trailing text'
    assert _extract_json(prefixed)["x"]["y"] == [1]
