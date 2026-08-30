"""Deep-dive pipeline orchestration, with the LLM and web client mocked."""

from __future__ import annotations

import json

import pytest

import ptm.deepsearch.research as research_mod
from ptm.deepsearch.pipeline import run_deep_dive


@pytest.fixture
def mock_llm(monkeypatch):
    """chat_json returns a canned payload per system prompt."""
    calls = []

    def fake_chat_json(system, user, **kwargs):
        calls.append(system[:60])
        if "planning a deep-dive" in system:
            return {"queries": ["TEST latest earnings", "TEST competitor moves"]}
        if "extracting findings" in system:
            return {"findings": [{"claim": "Revenue up 40% y/y", "source_idx": 1, "category": "business", "dated": "2026-08-01"}]}
        if "key qualitative drivers" in system:
            return {"drivers": [{"name": "Pricing power", "bull_read": "guidance raised", "bear_read": "rivals undercut"}]}
        if "STRONGEST HONEST case" in system:
            key = "strength" if "BULL case" in user else "severity"
            return {"points": [{"point": "Main point", "evidence": "ev", "finding_idx": 1, key: "strong" if key == "strength" else "material"}]}
        if "moderating a structured" in system:
            return {
                "rounds": [{"driver": "Pricing power", "bull": "b", "bull_finding_idx": 1, "bear": "r", "bear_finding_idx": 1,
                            "verdict": "bull wins", "verdict_side": "bull", "falsifier": "growth < 20%"}],
                "confidence": "high",
                "confidence_why": "consistent sources",
            }
        if "final view" in system:
            return {
                "stance": "constructive",
                "thesis": "Acceleration is real.",
                "drivers": [{"name": "Pricing power", "direction": "tailwind", "evidence": "ev", "source_idx": 1, "confidence": "high"}],
                "falsifiers": ["growth < 20%"],
                "confidence": "high",
                "confidence_why": "consistent",
            }
        if "catalysts" in system:
            return {"catalysts": [{"event": "Q3 print", "window": "Nov", "expected": "beat/miss", "finding_idx": 1}]}
        return {}

    monkeypatch.setattr("ptm.deepsearch.research.chat_json", fake_chat_json)
    monkeypatch.setattr("ptm.deepsearch.analysis.chat_json", fake_chat_json)
    monkeypatch.setattr("ptm.deepsearch.pipeline.chat_json", fake_chat_json)
    return calls


@pytest.fixture
def mock_web(monkeypatch):
    """web_search returns one result per query; web_fetch returns a transcript page."""
    searches = []

    def fake_search(query, max_results=8, use_cache=True):
        searches.append(query)
        return [{"title": f"Result for {query}", "url": f"https://example.com/{query.replace(' ', '-')}", "content": "Revenue up 40% y/y. Guidance raised."}]

    def fake_fetch(url, use_cache=True):
        return {"title": "Transcript", "content": "CEO: demand remains strong. Backlog up 22%."}

    monkeypatch.setattr(research_mod, "web_search", fake_search)
    monkeypatch.setattr(repath := research_mod, "web_fetch", fake_fetch)
    monkeypatch.setattr("ptm.deepsearch.pipeline.filing_context", lambda ticker, max_chars=6000: "Filing text")
    return searches


def test_full_dive_happy_path(mock_llm, mock_web, tmp_path):
    result = run_deep_dive("TEST", name="Test Corp", sector="Tech", force=True)
    assert result.error == ""
    assert result.llm_used is True
    assert len(mock_web) == 2  # both planned queries ran
    assert result.research is not None and len(result.research.findings) >= 1
    assert result.thesis is not None
    assert result.thesis.stance == "constructive"
    assert len(result.thesis.debate) == 1
    assert result.thesis.falsifiers == ["growth < 20%"]
    assert result.catalysts and result.catalysts[0].event == "Q3 print"


def test_dive_is_cached(mock_llm, mock_web, tmp_path):
    first = run_deep_dive("TEST", force=True)
    assert first.error == ""
    searches_before = len(mock_web)
    second = run_deep_dive("TEST")  # no force
    assert second.llm_used is True
    assert len(mock_web) == searches_before  # no new searches


def test_floor_keeps_this_campaigns_caches_under_force(mock_llm, mock_web, monkeypatch):
    """An interrupted redo must not re-dive what it already completed.

    force=True normally ignores the cache; with DEEPSEARCH_CACHE_FLOOR set,
    caches written after the floor are the redo's own work and stay.
    """
    from time import time

    from ptm.config import env as settings_env

    first = run_deep_dive("TEST", force=True)  # "the campaign ran once"
    assert first.error == ""
    searches_before = len(mock_web)
    monkeypatch.setenv("DEEPSEARCH_CACHE_FLOOR", str(time() - 10))  # cache is newer
    settings_env.cache_clear()
    resumed = run_deep_dive("TEST", force=True)
    assert resumed.llm_used is True
    assert len(mock_web) == searches_before, "post-floor cache must be kept even under force"
    monkeypatch.setenv("DEEPSEARCH_CACHE_FLOOR", str(time() + 60))  # cache predates the floor
    settings_env.cache_clear()
    redone = run_deep_dive("TEST", force=True)
    assert len(mock_web) > searches_before, "pre-floor cache must be re-dived"


def test_no_llm_key_fails_clean(mock_web, monkeypatch):
    monkeypatch.setattr("ptm.deepsearch.pipeline.llm_available", lambda: False)
    result = run_deep_dive("TEST", force=True)
    assert "no LLM key" in result.error
    assert result.thesis is None


def test_no_search_results_fails_clean(mock_llm, monkeypatch):
    monkeypatch.setattr(research_mod, "web_search", lambda *a, **k: [])
    result = run_deep_dive("TEST", force=True)
    assert result.error != ""
    assert result.thesis is None
    assert "returned no results" in result.error  # genuinely empty, not rate-limited


def test_rate_limited_search_named_as_such(mock_llm, monkeypatch):
    """A provider 429 storm must not masquerade as an empty search."""
    import requests as _r

    def throttled(*a, **k):
        raise _r.HTTPError("429 Client Error: too many requests")

    monkeypatch.setattr(research_mod, "web_search", throttled)
    result = run_deep_dive("TEST", force=True)
    assert result.thesis is None
    assert "rate-limited" in result.error, f"429 surfaced as: {result.error}"


def test_stage_failure_degrades_not_dies(mock_llm, mock_web, monkeypatch):
    # Debate fails; synthesis should still run on empty rounds.
    def boom(*a, **k):
        raise RuntimeError("provider 500")

    monkeypatch.setattr("ptm.deepsearch.analysis.run_debate", boom)
    result = run_deep_dive("TEST", force=True)
    assert result.thesis is not None
    assert result.thesis.debate == []
    assert "debate failed" in result.thesis.confidence_why