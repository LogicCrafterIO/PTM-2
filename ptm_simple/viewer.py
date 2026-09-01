"""Viewer glue for the simple process: state, workers, and endpoint handlers.

Kept inside ptm_simple so the PTM viewer server stays generic — it only
delegates /api/simple/* here. One simple action at a time; the dive-bearing
`run` action additionally refuses to start while a deep-dive batch or an
idea pipeline is in flight, so nothing ever hammers the LLM in parallel.
"""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone

from ptm.log import log

_SIMPLE_ACTIONS = ("build-themes", "build-wiki", "radar", "run")
_lock = threading.Lock()
_state: dict = {
    "running": False,
    "kind": "",
    "started": "",
    "finished": "",
    "error": "",
    "elapsed_s": 0,
    "events": [],
    "result": None,
}
_started_mono = 0.0


def status() -> dict:
    snap = dict(_state)
    snap["events"] = list(_state.get("events") or [])
    if snap["running"] and _started_mono:
        snap["elapsed_s"] = round(time.monotonic() - _started_mono, 1)
    snap["artifacts"] = artifacts()
    return snap


def _append_event(line: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with _lock:
        events = list(_state.get("events") or [])
        events.append({"t": now, "line": line})
        _state["events"] = events[-400:]


def _worker(action: str, opts: dict) -> None:
    started = time.monotonic()
    sink = lambda line: _append_event(line)  # noqa: E731
    try:
        from ptm.asof import as_of_date
        from ptm.log import add_sink, remove_sink

        add_sink(sink)
        ref = as_of_date()
        result: dict | None = None
        if action == "build-themes":
            from ptm_simple.thememap import build_theme_map

            out = build_theme_map(opts.get("xlsx") or "John pre mentoring starterpack.xlsx")
            result = {"themes": out["theme_count"], "tickers": out["ticker_count"], "source": "xlsx clusters"}
        elif action == "build-wiki":
            from ptm_simple.wiki_themes import build_theme_map_wiki

            out = build_theme_map_wiki()
            result = {
                "themes": out["theme_count"], "tickers": out["ticker_count"],
                "fallbacks": out.get("wiki_fallbacks", 0), "source": "wikipedia-industry",
            }
        elif action == "radar":
            from ptm_simple.radar import run_radar, write_radar
            from ptm_simple.run import load_theme_map
            from ptm_simple.whynow import grade_radar

            theme_map = load_theme_map(opts.get("map") or "manual")
            rows = run_radar(theme_map, ref, refresh=int(opts.get("refresh") or 0))
            if opts.get("llm"):
                grade_radar(rows, only=opts.get("theme"))
            rows = [r for r in rows if not opts.get("theme") or r["theme"] == opts.get("theme")]
            write_radar(rows, ref)
            counted = [r for r in rows if r["status"] != "COLD"]
            result = {
                "active": sum(1 for r in counted if r["status"] == "ACTIVE"),
                "warm": sum(1 for r in counted if r["status"] == "WARM"),
                "themes_total": len(rows),
            }
        elif action == "run":
            from ptm_simple.run import load_theme_map, run_theme_pass

            theme_map = load_theme_map(opts.get("map") or "manual")
            payload = run_theme_pass(theme_map, opts.get("theme") or "", ref, force=bool(opts.get("force")))
            result = {"book": len(payload["book"]), "parked": len(payload["overflow"]),
                      "ideas": payload["book"], "overflow": payload["overflow"]}
        else:
            raise ValueError(f"unknown simple action: {action}")
        with _lock:
            _state["result"] = result
    except SystemExit as exc:  # the CLI-style guards raise SystemExit with a message
        with _lock:
            _state["error"] = str(exc)[:400]
    except Exception as exc:
        log(f"viewer simple {action}: FAILED {exc}")
        with _lock:
            _state["error"] = str(exc)[:400]
    finally:
        try:
            from ptm.log import remove_sink

            remove_sink(sink)
        except Exception:
            pass
        with _lock:
            _state["running"] = False
            _state["finished"] = datetime.now(timezone.utc).isoformat()
            _state["elapsed_s"] = round(time.monotonic() - started, 1)


def start(action: str, opts: dict, other_work_running: bool = False) -> tuple[bool, dict, int]:
    """Start a simple action. `other_work_running` is the server's own deep
    dive / pipeline busy flag: a theme pass dives tickers, so it must not
    start on top of another LLM consumer."""
    if action not in _SIMPLE_ACTIONS:
        return False, {"error": f"action must be one of {list(_SIMPLE_ACTIONS)}"}, 400
    if other_work_running and action == "run":
        return False, {"error": "a deep-dive batch or idea pipeline is running; dives would collide"}, 409
    with _lock:
        if _state["running"]:
            return False, {"error": "a simple-process action is already running", "status": dict(_state)}, 409
        global _started_mono
        _started_mono = time.monotonic()
        _state.update(running=True, kind=action, started=datetime.now(timezone.utc).isoformat(),
                      finished="", error="", elapsed_s=0, events=[], result=None)
    threading.Thread(target=_worker, args=(action, opts), daemon=True).start()
    return True, {"started": True, "action": action}, 200


# ---------------------------------------------------------------- artifacts

def _read_json(path):
    from ptm.io import read_json

    try:
        return read_json(path)
    except Exception:
        return None


def artifacts() -> dict:
    """What simple-process artifacts exist right now, for the viewer."""
    from ptm.config import data_dir

    sdir = data_dir("simple")
    arts: dict = {"maps": {}, "radar_files": [], "radar_date": None, "book": None, "watchlist": None}
    for source, name in (("manual", "theme_map.json"), ("wiki", "theme_map_wiki.json")):
        path = sdir / name
        if not path.exists():
            arts["maps"][source] = {"exists": False, "name": name}
            continue
        payload = _read_json(path)
        if not isinstance(payload, dict):
            arts["maps"][source] = {"exists": False, "name": name, "error": "unreadable"}
            continue
        arts["maps"][source] = {
            "exists": True,
            "name": name,
            "kind": "Wikipedia industries" if source == "wiki" else "xlsx clusters",
            "themes": payload.get("theme_count"),
            "tickers": payload.get("ticker_count"),
            "fallbacks": payload.get("wiki_fallbacks", 0),
            "mtime": time.strftime("%Y-%m-%d %H:%M", time.localtime(path.stat().st_mtime)),
        }
    for path in sorted(sdir.glob("radar_*.json"), key=lambda p: p.stat().st_mtime):
        arts["radar_files"].append(path.stem.replace("radar_", ""))
    if arts["radar_files"]:
        arts["radar_date"] = arts["radar_files"][-1]
    book = _latest_file(sdir, "simple_book_*.json")
    if book:
        payload = _read_json(book) or {}
        arts["book"] = {"file": book.name, "as_of": payload.get("as_of"),
                        "ideas": len(payload.get("book") or []), "overflow": len(payload.get("overflow") or [])}
    watch = sdir / "watchlist.json"
    if watch.exists():
        payload = _read_json(watch) or {}
        arts["watchlist"] = {"parked": len(payload.get("parked") or [])}
    ideadir = ideas_dir_simple()
    arts["reports"] = sum(1 for _ in ideadir.rglob("*.md")) if ideadir.exists() else 0
    return arts


def _latest_file(sdir, pattern: str):
    files = sorted(sdir.glob(pattern), key=lambda p: p.stat().st_mtime)
    return files[-1] if files else None


def ideas_dir_simple():
    from ptm_simple import simple_ideas_dir

    return simple_ideas_dir()


def get_theme_map(source: str) -> dict:
    from ptm.config import data_dir

    source = (source or "manual").lower()
    if source not in ("manual", "wiki"):
        return {"error": f"source must be 'manual' or 'wiki', got '{source}'"}
    name = "theme_map_wiki.json" if source == "wiki" else "theme_map.json"
    path = data_dir("simple", name)
    if not path.exists():
        return {"error": f"no theme map for source '{source}': build it first"}
    payload = _read_json(path) or {}
    return {"source": source, "map": payload}


def get_radar(date_str: str | None = None) -> dict:
    from ptm.config import data_dir

    sdir = data_dir("simple")
    if date_str:
        path = sdir / f"radar_{date_str}.json"
        if not path.exists():
            return {"error": f"no radar for {date_str}"}
        return {"radar": _read_json(path)}
    files = sorted(sdir.glob("radar_*.json"), key=lambda p: p.stat().st_mtime)
    if not files:
        return {"error": "no radar yet: run the radar first"}
    return {"radar": _read_json(files[-1])}


def get_theme_detail(name: str, source: str) -> dict:
    """Live radar row + deterministic shortlist for one theme."""
    from datetime import date as _date

    from ptm.asof import as_of_date
    from ptm_simple.radar import theme_radar
    from ptm_simple.run import load_theme_map, select_theme, theme_entry

    ref = as_of_date()
    theme_map = load_theme_map(source)
    entry = theme_entry(theme_map, name)
    if entry is None:
        return {"error": f"theme '{name}' not in the {source} map"}
    from ptm_simple.run import _fundamentals

    row = theme_radar(entry, _fundamentals(), ref)
    sel = select_theme(theme_map, name, ref)
    return {"row": {k: v for k, v in row.items() if k != "members"}, "members": row["members"], "selection": sel, "ref": ref.isoformat()}


def get_book() -> dict:
    from ptm.config import data_dir

    book = _latest_file(data_dir("simple"), "simple_book_*.json")
    if not book:
        return {"error": "no book yet: run a theme pass"}
    return {"book": _read_json(book) or {}, "file": book.name}


def get_watchlist() -> dict:
    from ptm.config import data_dir

    path = data_dir("simple", "watchlist.json")
    if not path.exists():
        return {"parked": [], "as_of": None}
    return _read_json(path) or {"parked": []}


def list_reports() -> dict:
    ideadir = ideas_dir_simple()
    reports = []
    if ideadir.exists():
        for path in sorted(ideadir.rglob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True):
            rel = str(path.relative_to(ideadir))
            reports.append({"path": rel, "mtime": time.strftime("%Y-%m-%d %H:%M", time.localtime(path.stat().st_mtime))})
    return {"reports": reports, "dir": str(ideadir)}


def read_report(rel: str) -> dict:
    ideadir = ideas_dir_simple().resolve()
    path = (ideadir / rel).resolve()
    if not str(path).startswith(str(ideadir)) or not path.is_file():
        return {"error": "not found"}
    return {"path": rel, "markdown": path.read_text()}