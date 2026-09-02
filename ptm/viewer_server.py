"""Local server for the PTM viewer.

Serves the repo (viewer/, data/curated, ideas/) over HTTP — the same files the
manual `python -m http.server` workflow served — plus a small JSON API so the
Deep Dives tab can list, read, and GENERATE deep-dive reports from the browser,
and the Pipeline tab can run the full idea pipeline (whose qualitative pass now
IS the deep dive).

    GET  /                          -> viewer/index.html
    GET  /api/deepdive/list         -> cached dives with metadata
    GET  /api/deepdive/report/<T>   -> {ticker, markdown} for one cached dive
    GET  /api/deepdive/status       -> batch generation progress
    POST /api/deepdive/generate     -> body {"tickers": ["PLTR", ...]}
    GET  /api/pipeline/status       -> idea-pipeline run progress and result
    POST /api/pipeline/run          -> body {"mode": "weekly"|"ideas", ...}

    GET  /api/simple/status          -> simple-process action state + artifact inventory
    GET  /api/simple/theme-map/<src> -> manual|wiki theme map payload
    GET  /api/simple/radar[?date=]   -> latest (or dated) radar rows
    GET  /api/simple/theme/<name>    -> live radar row + selection for one theme (?source=)
    GET  /api/simple/quant           -> deterministic quant table (P/S, EPS1/2, PE1/2, PEG1/2)
    GET  /api/simple/review          -> latest per-theme group review (are the flags justified?)
    GET  /api/simple/reports         -> idea-report files
    GET  /api/simple/report/<rel>    -> one idea report's markdown
    POST /api/simple/run             -> body {"action": "build-themes"|"build-wiki"|"radar"|"refresh-fundamentals"|"analyze-all"|"group-review", ...}

The simple-process handlers live in ptm_simple.viewer; this server only
delegates. A simple `run` (which dives tickers) is refused while a deep-dive
batch or an idea pipeline is in flight, same exclusivity as the other tabs.

Both run the real pipeline in background threads; the deep-dive batch and an
idea-pipeline run are mutually exclusive, so the two can never hammer the LLM
at once. Run from the repo root:

    python -m ptm viewer --port 8765
"""

from __future__ import annotations

import json
import re
import threading
import time
import urllib.parse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from ptm.config import ROOT, data_dir, ideas_dir
from ptm.log import log

# Live dive progress, parsed from the pipeline's own log lines as they stream
# past (the same lines the viewer shows). Kept as O(1) state per ticker so the
# Pipeline tab can show every concurrent dive's current stage even after those
# lines have scrolled out of the log ring.
_PIPE_DIVE_RE = re.compile(r"deepdive (\S+): (\S+)(?: — (.*))?")
_PIPE_STAGED_RE = re.compile(r"idea (\S+): deep dive staged")
_PIPE_FAIL_RE = re.compile(r"idea (\S+): deep dive FAIL")
_PIPE_IDEA_RE = re.compile(r"idea (\d+)/(\d+) ")

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

# One idea-pipeline run at a time, with its own live log tail. `events` carries
# timestamped lines from ptm.log while the run is active; `result` is the run
# summary dict (the same JSON `ptm weekly` prints) once it finishes. `dives`
# tracks in-flight deep dives (ticker -> {stage, detail, since, seq}); staged/
# failed count finished dives; ideas_started/total feed the progress bar.
_pipe_lock = threading.Lock()
_pipe_state: dict = {
    "running": False,
    "mode": "",
    "qual_mode": "",
    "started": "",
    "finished": "",
    "error": "",
    "elapsed_s": 0,
    "events": [],
    "result": None,
    "done": [],
    "staged": 0,
    "failed": 0,
    "ideas_started": 0,
    "ideas_total": 0,
    "dives": {},
}
_started_mono = 0.0


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


def _idea_meta(ticker: str) -> dict:
    """The candidate side + earnings window this dive's idea was staged under.

    Sourced from the idea artifacts (the same place the Ideas tab reads), so
    the Deep-dives tab can filter long/short and by catalyst window without
    duplicating the candidate set. Newest idea file wins; empty strings when
    the idea was never staged.
    """
    best = (0.0, "", "")
    try:
        paths = list(ideas_dir().glob(f"*/*/*/*_{ticker}.json"))
    except Exception:
        paths = []
    for path in paths:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            cand = payload.get("candidate") or {}
        except Exception:
            continue
        mtime = path.stat().st_mtime
        if mtime > best[0]:
            best = (mtime, str(cand.get("side") or ""), str(path.parts[-2]))
    return {"side": best[1], "window": best[2]}


def _dive_score(payload: dict) -> dict | None:
    """The dive's qual evidence score, computed by the SAME code the scorecard
    uses — not a re-derivation, so the card can never disagree with the report.

    The synthesis (or, for older dives, the debate-verdict fallback) scored
    each driver; driver_rows + aggregate_scores apply the fixed category
    weights and mirror to long/short. None when the dive scores nothing.
    """
    try:
        from ptm.deepsearch.models import DeepResult
        from ptm.deepsearch.verdict import aggregate_scores, driver_rows

        result = DeepResult.model_validate(payload)
        rows = driver_rows(result.thesis)
        if not rows:
            return None
        agg = aggregate_scores(rows)
        return {"s": agg["s"], "long": agg["long"], "short": agg["short"]}
    except Exception:
        return None


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
        meta = _idea_meta(ticker)
        items.append(
            {
                "ticker": ticker,
                "name": str(payload.get("name") or ""),
                "sector": str(payload.get("sector") or ""),
                "as_of": str(payload.get("as_of") or ""),
                "score": _dive_score(payload),
                "confidence": str(thesis.get("confidence") or ""),
                "side": meta["side"],
                "window": meta["window"],
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


# --- Idea-pipeline runs (the deep-dive qualitative is part of the pipeline) ---

def _append_pipe_event(line: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with _pipe_lock:
        events = _pipe_state.get("events") or []
        events.append({"t": now, "line": line})
        _pipe_state["events"] = events[-3000:]
        # Fold the line into the live dive/idea progress. Cheap regexes against
        # a string we were already holding; keeps counters exact even after old
        # log lines drop out of the ring.
        m = _PIPE_IDEA_RE.search(line)
        if m:
            try:
                done_n, total_n = int(m.group(1)), int(m.group(2))
            except ValueError:
                done_n = total_n = 0
            if total_n > 0:
                _pipe_state["ideas_total"] = total_n
            _pipe_state["ideas_started"] = max(_pipe_state["ideas_started"], done_n)
            return
        m = _PIPE_STAGED_RE.search(line)
        if m:
            _pipe_state["staged"] += 1
            _pipe_state["dives"].pop(m.group(1), None)
            return
        m = _PIPE_FAIL_RE.search(line)
        if m:
            _pipe_state["failed"] += 1
            _pipe_state["dives"].pop(m.group(1), None)
            return
        m = _PIPE_DIVE_RE.search(line)
        if m:
            ticker, stage, detail = m.group(1), m.group(2), (m.group(3) or "").strip()
            seq = len(_pipe_state["dives"])
            prev = _pipe_state["dives"].get(ticker)
            if prev:
                # Same ticker, same stage: keep the original start time but
                # refresh the detail line (query 4/8 etc. stream through it).
                seq = prev.get("seq", seq)
                since = prev["since"] if prev.get("stage") == stage else now
            else:
                since = now
            _pipe_state["dives"][ticker] = {"stage": stage, "detail": detail, "since": since, "seq": seq}


def _pipeline_worker(mode: str, opts: dict) -> None:
    started = time.monotonic()
    sink = lambda line: _append_pipe_event(line)  # noqa: E731
    try:
        from ptm.log import add_sink, remove_sink

        add_sink(sink)
        if mode == "weekly":
            from ptm.pipeline import run

            result = run(
                max_tickers=opts.get("max_tickers"),
                max_candidates=opts.get("max_candidates"),
                skip_llm=bool(opts.get("skip_llm")),
                force=bool(opts.get("force")),
                qual_mode="legacy" if opts.get("legacy_qual") else "deepdive",
                dd_force=bool(opts.get("dd_force")),
            )
        else:
            from ptm.pipeline import generate_ideas

            result = {
                "mode": "ideas",
                "ideas": len(
                    generate_ideas(
                        max_candidates=opts.get("max_candidates"),
                        skip_llm=bool(opts.get("skip_llm")),
                        qual_mode="legacy" if opts.get("legacy_qual") else "deepdive",
                        dd_force=bool(opts.get("dd_force")),
                    )
                ),
                "note": "books rebuilt from the fresh ideas; ingest left untouched",
            }
        with _pipe_lock:
            _pipe_state["result"] = result
    except Exception as exc:
        log(f"viewer pipeline run: FAILED {exc}")
        with _pipe_lock:
            _pipe_state["error"] = str(exc)[:400]
    finally:
        remove_sink(sink)
        with _pipe_lock:
            _pipe_state["running"] = False
            _pipe_state["finished"] = datetime.now(timezone.utc).isoformat()
            _pipe_state["elapsed_s"] = round(time.monotonic() - started, 1)


def _start_pipeline(mode: str, opts: dict) -> tuple[bool, dict]:
    """Start a pipeline run unless the server is already busy elsewhere."""
    if mode not in {"weekly", "ideas"}:
        return False, {"error": "mode must be 'weekly' or 'ideas'"}
    max_candidates = opts.get("max_candidates")
    if max_candidates not in (None, ""):
        try:
            opts["max_candidates"] = max(1, int(max_candidates))
        except (TypeError, ValueError):
            return False, {"error": "max_candidates must be an integer"}
    else:
        opts["max_candidates"] = None
    max_tickers = opts.get("max_tickers")
    if max_tickers not in (None, ""):
        try:
            opts["max_tickers"] = max(1, int(max_tickers))
        except (TypeError, ValueError):
            return False, {"error": "max_tickers must be an integer"}
    else:
        opts["max_tickers"] = None
    with _pipe_lock:
        if _pipe_state["running"]:
            return False, {"error": "a pipeline run is already in progress", "status": dict(_pipe_state)}
        with _lock:
            if _state["running"]:
                return False, {"error": "a deep-dive batch is running; wait for it to finish first"}
        global _started_mono
        _started_mono = time.monotonic()
        _pipe_state.update(
            running=True,
            mode=mode,
            qual_mode="legacy" if opts.get("legacy_qual") else "deepdive",
            started=datetime.now(timezone.utc).isoformat(),
            finished="",
            error="",
            elapsed_s=0,
            events=[],
            result=None,
            done=[],
            staged=0,
            failed=0,
            ideas_started=0,
            ideas_total=0,
            dives={},
        )
    threading.Thread(target=_pipeline_worker, args=(mode, opts), daemon=True).start()
    return True, {"started": True, "mode": mode}


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
        query = urllib.parse.parse_qs(self.path.split("?")[1]) if "?" in self.path else {}
        if route in ("/", "/viewer"):
            self._serve_file("viewer/index.html")
        elif route == "/api/deepdive/list":
            self._json({"reports": _list_reports()})
        elif route.startswith("/api/deepdive/report/"):
            self._json(_read_report(route.rsplit("/", 1)[-1].upper()))
        elif route == "/api/deepdive/status":
            with _lock:
                self._json(dict(_state))
        elif route == "/api/pipeline/status":
            with _pipe_lock:
                snap = dict(_pipe_state)
                snap["dives"] = dict(_pipe_state.get("dives") or {})
                if snap["running"] and _started_mono:
                    # Live elapsed while running; the final value is set exactly once
                    # in the worker's finally block.
                    snap["elapsed_s"] = round(time.monotonic() - _started_mono, 1)
            self._json(snap)
        elif route == "/api/simple/status":
            from ptm_simple import viewer as simple

            self._json(simple.status())
        elif route.startswith("/api/simple/theme-map/"):
            from ptm_simple import viewer as simple

            self._json(simple.get_theme_map(route.rsplit("/", 1)[-1].lower()))
        elif route == "/api/simple/radar":
            from ptm_simple import viewer as simple

            self._json(simple.get_radar((query.get("date") or [None])[0]))
        elif route.startswith("/api/simple/report/"):
            from ptm_simple import viewer as simple

            rel = urllib.parse.unquote(route.removeprefix("/api/simple/report/"))
            self._json(simple.read_report(rel))
        elif route == "/api/simple/reports":
            from ptm_simple import viewer as simple

            self._json(simple.list_reports())
        elif route == "/api/simple/quant":
            from ptm_simple import viewer as simple

            self._json(simple.get_quant())
        elif route == "/api/simple/review":
            from ptm_simple import viewer as simple

            self._json(simple.get_review())
        elif route.startswith("/api/simple/theme/"):
            from ptm_simple import viewer as simple

            name = urllib.parse.unquote(route.removeprefix("/api/simple/theme/"))
            source = (query.get("source") or ["manual"])[0]
            self._json(simple.get_theme_detail(name, source))
        else:
            # Everything else is a static file from the repo root.
            rel = route.lstrip("/")
            if rel.startswith(("data/", "ideas/", "viewer/")):
                self._serve_file(rel)
            else:
                self._json({"error": "not found"}, 404)

    def do_POST(self) -> None:
        route = self.path.rstrip("/")
        if route == "/api/pipeline/run":
            length = int(self.headers.get("Content-Length") or 0)
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
            except Exception:
                self._json({"error": "invalid JSON body"}, 400)
                return
            opts = {
                "max_candidates": body.get("max_candidates"),
                "max_tickers": body.get("max_tickers"),
                "skip_llm": bool(body.get("skip_llm")),
                "force": bool(body.get("force")),
                "legacy_qual": bool(body.get("legacy_qual")),
                "dd_force": bool(body.get("dd_force")),
            }
            ok, payload = _start_pipeline(str(body.get("mode") or "ideas"), opts)
            self._json(payload, 200 if ok else (409 if "already" in payload.get("error", "") else 400))
            return
        if route == "/api/simple/run":
            length = int(self.headers.get("Content-Length") or 0)
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
            except Exception:
                self._json({"error": "invalid JSON body"}, 400)
                return
            from ptm_simple import viewer as simple

            opts = {
                "map": str(body.get("map") or "manual"),
                "theme": str(body.get("theme") or ""),
                "xlsx": str(body.get("xlsx") or "John pre mentoring starterpack.xlsx"),
                "force": bool(body.get("force")),
                "llm": bool(body.get("llm")),
                "refresh": body.get("refresh"),
            }
            ok, payload, code = simple.start(
                str(body.get("action") or ""), opts,
                other_work_running=_pipe_state["running"] or _state["running"],
            )
            self._json(payload, 200 if ok else code)
            return
        if route != "/api/deepdive/generate":
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
        with _pipe_lock:
            if _pipe_state["running"]:
                self._json(
                    {"error": "an idea-pipeline run is in progress; wait for it to finish first"},
                    409,
                )
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