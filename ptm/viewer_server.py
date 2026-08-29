"""Local server for the PTM viewer.

Serves the repo (viewer/, data/curated, ideas/) over HTTP — the same files the
manual `python -m http.server` workflow served — plus a small JSON API so the
Deep Dives tab can list, read, and GENERATE deep-dive reports from the browser.

    GET  /                          -> viewer/index.html
    GET  /api/deepdive/list         -> cached dives with metadata
    GET  /api/deepdive/report/<T>   -> {ticker, markdown} for one cached dive
    GET  /api/deepdive/status       -> batch generation progress
    POST /api/deepdive/generate     -> body {"tickers": ["PLTR", ...]}

Generation runs the real pipeline in a background thread, one ticker at a
time, in the order entered. Run from the repo root:

    python -m ptm viewer --port 8765
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from ptm.config import ROOT, data_dir, ideas_dir
from ptm.log import log

_lock = threading.Lock()
# Batch state plus the live per-ticker stage. `stage` holds what the pipeline
# is doing right now for the ticker in `current`: {stage, detail, since}.
_state: dict = {
    "running": False,
    "queue": [],
    "current": "",
    "stage": "",
    "detail": "",
    "stage_since": "",
    "done": [],
    "started": "",
    "error": "",
    "events": [],
}


def _report_progress(ticker: str, stage: str, detail: str) -> None:
    """Stage updates from the pipeline, called on the worker thread."""
    with _lock:
        if _state.get("current") == ticker:
            _state["stage"] = stage
            _state["stage_detail"] = detail
            _state["stage_since"] = datetime.now(timezone.utc).isoformat()
            events = _state.get("events") or []
            events.append(
                {"t": _state["stage_since"], "ticker": ticker, "stage": stage, "detail": detail}
            )
            _state["events"] = events[-400:]  # cap the log a long batch can accumulate


def _identity(ticker: str) -> tuple[str, str, str]:
    """(sector, industry, name) from the curated universe, or blanks."""
    try:
        import pandas as pd

        path = data_dir("curated", "universe.csv")
        if not path.exists():
            return "", "", ""
        frame = pd.read_csv(path)
        row = frame.loc[frame["ticker"] == ticker.upper()]
        if not len(row):
            return "", "", ""
        r0 = row.iloc[0]
        return str(r0.get("sector") or ""), str(r0.get("industry") or ""), str(r0.get("name") or "")
    except Exception:
        return "", "", ""


def _list_reports() -> list[dict]:
    """Cached dives with the metadata the UI list shows."""
    from ptm.io import read_json

    runs = data_dir("raw", "deepsearch", "runs")
    reports_dir = ideas_dir("deepdive")
    items: list[dict] = []
    if not runs.exists():
        return []
    for path in sorted(runs.glob("*.json")):
        try:
            payload = read_json(path)
        except Exception:
            continue
        ticker = str(payload.get("ticker") or path.stem)
        thesis = payload.get("thesis") or {}
        macro = payload.get("macro") or {}
        items.append(
            {
                "ticker": ticker,
                "name": str(payload.get("name") or ""),
                "sector": str(payload.get("sector") or ""),
                "as_of": str(payload.get("as_of") or ""),
                "stance": str(thesis.get("stance") or ""),
                "confidence": str(thesis.get("confidence") or ""),
                "findings": len((payload.get("research") or {}).get("findings") or []),
                "catalysts": len(payload.get("catalysts") or []),
                "debate_rounds": len((thesis or {}).get("debate") or []),
                "macro_available": bool(macro.get("available")),
                "error": str(payload.get("error") or ""),
                "has_report": (reports_dir / ticker / "REPORT.md").exists(),
            }
        )
    return items


def _read_report(ticker: str) -> dict:
    ticker = ticker.upper().strip()
    path = ideas_dir("deepdive", ticker) / "REPORT.md"
    if not path.exists():
        return {"ticker": ticker, "error": "no report generated for this ticker yet"}
    return {"ticker": ticker, "markdown": path.read_text(encoding="utf-8", errors="ignore")}


def _run_one(ticker: str, force: bool = False) -> dict:
    """One full dive + report write, with metadata resolved from the universe."""
    from ptm.deepsearch.pipeline import run_deep_dive
    from ptm.deepsearch.render import render_markdown

    sector, industry, name = _identity(ticker)

    def progress(stage: str, detail: str = "") -> None:
        _report_progress(ticker, stage, detail)

    result = run_deep_dive(
        ticker,
        name=name,
        sector=sector,
        industry=industry,
        force=force,
        progress=progress,
    )
    out_dir = ideas_dir("deepdive", ticker)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "REPORT.md").write_text(render_markdown(result), encoding="utf-8")
    return {
        "ticker": ticker,
        "ok": not result.error,
        "stance": result.thesis.stance if result.thesis else "",
        "confidence": result.thesis.confidence if result.thesis else "",
        "findings": len(result.research.findings) if result.research else 0,
        "error": result.error,
    }


def _batch_worker(tickers: list[str], force: bool = False) -> None:
    try:
        for ticker in tickers:
            with _lock:
                _state["current"] = ticker
                # Stage fields reset per ticker; _run_one's progress callback
                # sets them as the pipeline advances.
                _state["stage"] = "queued"
                _state["stage_detail"] = ""
                _state["stage_since"] = datetime.now(timezone.utc).isoformat()
            try:
                entry = _run_one(ticker, force=force)
            except Exception as exc:
                entry = {"ticker": ticker, "ok": False, "stance": "", "findings": 0, "error": str(exc)[:300]}
            with _lock:
                _state["done"].append(entry)
                _state["current"] = ""
                _state["stage"] = ""
    finally:
        with _lock:
            _state["running"] = False
            _state["current"] = ""
            _state["stage"] = ""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args) -> None:
        pass  # per-request noise stays off the console; failures reach the UI

    def _json(self, payload: dict, code: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_file(self, rel: str) -> None:
        path = (ROOT / rel).resolve()
        if not str(path).startswith(str(ROOT)) or not path.is_file():
            self._json({"error": "not found"}, 404)
            return
        kind = {
            ".html": "text/html",
            ".js": "text/javascript",
            ".css": "text/css",
            ".json": "application/json",
            ".csv": "text/csv",
            ".md": "text/markdown",
            ".png": "image/png",
        }.get(path.suffix, "application/octet-stream")
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        route = self.path.split("?")[0].rstrip("/") or "/"
        if route in ("/", "/viewer"):
            self._serve_file("viewer/index.html")
        elif route == "/api/deepdive/list":
            self._json({"reports": _list_reports()})
        elif route.startswith("/api/deepdive/report/"):
            self._json(_read_report(route.rsplit("/", 1)[-1].upper()))
        elif route == "/api/deepdive/status":
            with _lock:
                self._json(dict(_state))
        else:
            # Everything else is a static file from the repo root.
            rel = route.lstrip("/")
            if rel.startswith(("data/", "ideas/", "viewer/")):
                self._serve_file(rel)
            else:
                self._json({"error": "not found"}, 404)

    def do_POST(self) -> None:
        if self.path.rstrip("/") != "/api/deepdive/generate":
            self._json({"error": "not found"}, 404)
            return
        length = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except Exception:
            self._json({"error": "invalid JSON body"}, 400)
            return
        raw = body.get("tickers") or []
        tickers: list[str] = []
        seen: set[str] = set()
        for item in raw:
            text = str(item or "").strip().upper()
            if text and text not in seen:
                seen.add(text)
                tickers.append(text)
        if not tickers:
            self._json({"error": "no tickers given"}, 400)
            return
        if len(tickers) > 25:
            self._json({"error": "at most 25 tickers per batch"}, 400)
            return
        with _lock:
            if _state["running"]:
                self._json({"error": "a batch is already running", "status": dict(_state)}, 409)
                return
            _state.update(
                running=True,
                queue=list(tickers),
                current="",
                stage="",
                stage_detail="",
                stage_since="",
                done=[],
                events=[],
                started=datetime.now(timezone.utc).isoformat(),
                error="",
            )
        threading.Thread(target=_batch_worker, args=(tickers,), kwargs={"force": bool(body.get("force"))}, daemon=True).start()
        self._json({"started": True, "tickers": tickers})


def serve(port: int = 8765) -> None:
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    log(f"viewer: serving http://127.0.0.1:{port}/  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log("viewer: stopped")