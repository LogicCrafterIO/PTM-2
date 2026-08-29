"""Ollama web client: response parsing, caching, error paths."""

from __future__ import annotations

import pytest

import ptm.deepsearch.web as web


@pytest.fixture(autouse=True)
def fake_env(monkeypatch):
    monkeypatch.setattr(web, "_key", lambda: "test-key")


def _post_stub(results=None, page=None):
    """Stand-in for requests.post matching the real call signature."""

    def handler(url, headers=None, json=None, timeout=None):
        class R:
            def raise_for_status(self):
                pass

            def json(self):
                if "web_search" in url:
                    return {"results": results or []}
                return page or {}

        return R()

    return handler


def test_search_parses_results(monkeypatch):
    monkeypatch.setattr(
        web.requests, "post",
        _post_stub(results=[
            {"title": "A", "url": "https://a.com", "content": "alpha"},
            {"title": "B", "url": "", "content": "dropped: no url"},
            {"title": "C", "url": "https://c.com", "content": "gamma"},
        ]),
    )
    results = web.web_search("PLTR earnings", max_results=3)
    assert [r["url"] for r in results] == ["https://a.com", "https://c.com"]


def test_fetch_parses_page(monkeypatch):
    monkeypatch.setattr(web.requests, "post", _post_stub(page={"title": "T", "content": "C"}))
    page = web.web_fetch("https://example.com/x")
    assert page == {"title": "T", "content": "C"}


def test_fetch_http_error_propagates(monkeypatch):
    def boom(url, headers=None, json=None, timeout=None):
        raise RuntimeError("429")

    monkeypatch.setattr(web.requests, "post", boom)
    with pytest.raises(RuntimeError):
        web.web_fetch("https://example.com/x", use_cache=False)


def test_search_block_renders_numbered():
    block = web.search_block([{"title": "A", "url": "https://a.com", "content": "x" * 900}], per_result=100)
    assert "[1] A" in block
    assert "https://a.com" in block
    assert len(block) < 300


def test_available_requires_key(monkeypatch):
    class NoKey:
        ollama_api_key = ""

    monkeypatch.setattr(web, "env", lambda: NoKey())
    assert web.available() is False