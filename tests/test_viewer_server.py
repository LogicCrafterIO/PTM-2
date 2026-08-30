"""Viewer server: report listing, reading, and identity resolution."""

from __future__ import annotations

import json

from ptm.viewer_server import _identity, _list_reports, _read_report


def _seed_run(isolate_roots, ticker: str, **overrides):
    from ptm.config import data_dir, ideas_dir
    from ptm.io import write_json

    payload = {
        "ticker": ticker,
        "name": f"{ticker} Corp",
        "sector": "Industrials",
        "industry": "Machinery",
        "as_of": "2026-08-29",
        "research": {"findings": [{"claim": "x"}] * 3, "queries_run": ["q"]},
        "thesis": {"stance": "cautious", "confidence": "medium", "debate": [{}, {}]},
        "macro": {"available": True},
        "catalysts": [{}, {}],
        "error": "",
    }
    payload.update(overrides)
    write_json(data_dir("raw", "deepsearch", "runs", f"{ticker}.json"), payload)
    report_dir = ideas_dir("deepdive", ticker)
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "REPORT.md").write_text(f"# {ticker} report\n\nTest body.\n", encoding="utf-8")
    return payload


def test_list_reports_reads_metadata(isolate_roots):
    _seed_run(isolate_roots, "TEST")
    items = _list_reports()
    assert len(items) == 1
    row = items[0]
    assert row["ticker"] == "TEST"
    assert row["stance"] == "cautious"
    assert row["findings"] == 3
    assert row["has_report"] is True


def test_read_report_returns_markdown(isolate_roots):
    _seed_run(isolate_roots, "TEST")
    out = _read_report("test")  # case-insensitive
    assert "error" not in out
    assert "# TEST report" in out["markdown"]


def test_read_report_missing(isolate_roots):
    out = _read_report("NOPE")
    assert "no report" in out["error"]


def test_identity_blank_on_missing_universe(isolate_roots):
    assert _identity("ZZZZ") == ("", "", "")


def test_batch_worker_generates_in_order(isolate_roots, monkeypatch):
    import ptm.viewer_server as vs

    calls = []

    def fake_run_one(ticker, force=False):
        calls.append(ticker)
        return {"ticker": ticker, "ok": True, "stance": "balanced", "findings": 5, "error": ""}

    monkeypatch.setattr(vs, "_run_one", fake_run_one)
    vs._batch_worker(["AAA", "BBB"], force=False)
    assert calls == ["AAA", "BBB"]  # order preserved
    assert vs._state["running"] is False
    assert [d["ticker"] for d in vs._state["done"]] == ["AAA", "BBB"]
    assert all(d["ok"] for d in vs._state["done"])


def test_batch_worker_survives_failure(isolate_roots, monkeypatch):
    import ptm.viewer_server as vs

    def fake_run_one(ticker, force=False):
        if ticker == "BAD":
            raise RuntimeError("provider exploded")
        return {"ticker": ticker, "ok": True, "stance": "cautious", "findings": 1, "error": ""}

    monkeypatch.setattr(vs, "_run_one", fake_run_one)
    vs._batch_worker(["GOOD", "BAD"], force=False)
    assert vs._state["running"] is False
    done = {d["ticker"]: d for d in vs._state["done"]}
    assert done["GOOD"]["ok"] is True
    assert done["BAD"]["ok"] is False
    assert "provider" in done["BAD"]["error"]


def test_pipeline_worker_streams_log_and_result(isolate_roots, monkeypatch):
    import ptm.viewer_server as vs

    def fake_generate_ideas(**kwargs):
        from ptm.log import log

        log("ideas: researching 2 of 40 PE candidates")
        return [object(), object()]

    monkeypatch.setattr("ptm.pipeline.generate_ideas", fake_generate_ideas)
    vs._pipeline_worker("ideas", {"legacy_qual": False, "dd_force": False})
    st = dict(vs._pipe_state)
    assert st["running"] is False
    assert st["result"]["ideas"] == 2
    assert any("researching 2 of 40" in e["line"] for e in st["events"])


def test_pipeline_start_busy_and_bad_mode(isolate_roots, monkeypatch):
    import ptm.viewer_server as vs

    vs._pipe_state["running"] = True
    try:
        ok, payload = vs._start_pipeline("ideas", {})
        assert ok is False and "already in progress" in payload["error"]
    finally:
        vs._pipe_state["running"] = False
    ok, payload = vs._start_pipeline("nope", {})
    assert ok is False and "mode" in payload["error"]
    ok, payload = vs._start_pipeline("ideas", {"max_candidates": "x"})
    assert ok is False and "max_candidates" in payload["error"]
    # A busy deep-dive batch blocks a pipeline start (never hammer the LLM twice).
    vs._state["running"] = True
    vs._pipe_state["running"] = False
    try:
        ok, payload = vs._start_pipeline("ideas", {})
        assert ok is False and "deep-dive batch" in payload["error"]
    finally:
        vs._state["running"] = False