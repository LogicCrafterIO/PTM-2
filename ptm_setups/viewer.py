"""Viewer glue for the ranking process: state, workers, and endpoint handlers.

Mirrors ptm_simple.viewer so the PTM viewer server stays generic — it only
delegates /api/setups/* here. One ranking action at a time, and the LLM-bearing
`rank` action additionally refuses to start while a deep-dive batch, an idea
pipeline or a simple-process action is in flight, so the provider is never hit
by two consumers at once.

The deterministic stages this tab offers (build either theme map, run the
radar, refresh fundamentals) are the SIMPLE process's own functions, writing
the same artifacts under data/simple/. That is deliberate: they are identical
computations, so running them from either tab updates one shared set of
numbers instead of two that can disagree. Only `rank` is this process's own.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone

from ptm.log import log

_SETUPS_ACTIONS = ("build-themes", "build-wiki", "radar", "refresh-fundamentals", "rank")
_LLM_ACTIONS = ("rank",)
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


def busy() -> bool:
    """True while a ranking action is running — the simple tab's exclusion check."""
    with _lock:
        return bool(_state["running"])


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
        from ptm.log import add_sink

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
            write_radar(rows, ref, theme_map)
            counted = [r for r in rows if r["status"] != "COLD"]
            result = {
                "active": sum(1 for r in counted if r["status"] == "ACTIVE"),
                "warm": sum(1 for r in counted if r["status"] == "WARM"),
                "themes_total": len(rows),
            }
        elif action == "refresh-fundamentals":
            from ptm_simple.refresh import refresh_fundamentals

            result = refresh_fundamentals(
                source=opts.get("map") or "manual",
                ref=ref,
                non_cold_only=not bool(opts.get("all")),
                force=bool(opts.get("force")),
                with_estimates=bool(opts.get("estimates")),
                with_prices=not bool(opts.get("no_prices")),
            )
        elif action == "rank":
            from ptm_setups.rank import run_setups

            result = run_setups(
                source=opts.get("map") or "manual",
                ref=ref,
                theme=opts.get("theme") or None,
                with_final=not bool(opts.get("no_final")),
                model=opts.get("model") or None,
            )
        else:
            raise ValueError(f"unknown setups action: {action}")
        with _lock:
            _state["result"] = result
    except SystemExit as exc:  # the CLI-style guards raise SystemExit with a message
        with _lock:
            _state["error"] = str(exc)[:400]
    except Exception as exc:
        log(f"viewer setups {action}: FAILED {exc}")
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
    """Start a ranking action. `other_work_running` is the server's own busy
    flag for the deep-dive batch, the idea pipeline and the simple process:
    `rank` is an LLM consumer, so it must not start on top of another one."""
    if action not in _SETUPS_ACTIONS:
        return False, {"error": f"action must be one of {list(_SETUPS_ACTIONS)}"}, 400
    if other_work_running and action in _LLM_ACTIONS:
        return False, {"error": "a deep-dive batch, idea pipeline or simple-process action is "
                                "running; the ranking pass would collide with it"}, 409
    with _lock:
        if _state["running"]:
            return False, {"error": "a ranking action is already running", "status": dict(_state)}, 409
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


def _latest_file(directory, pattern: str):
    if not directory.exists():
        return None
    files = sorted(directory.glob(pattern), key=lambda p: p.stat().st_mtime)
    return files[-1] if files else None


def ideas_dir_setups():
    from ptm_setups import setups_ideas_dir

    return setups_ideas_dir()


def artifacts() -> dict:
    """What this process can see right now: the shared inputs and its own output."""
    from ptm.config import data_dir

    sdir = data_dir("simple")
    arts: dict = {"maps": {}, "radar_date": None, "quant": None, "ranking": None, "reports": 0}
    for source, name in (("manual", "theme_map.json"), ("wiki", "theme_map_wiki.json")):
        path = sdir / name
        payload = _read_json(path) if path.exists() else None
        if not isinstance(payload, dict):
            arts["maps"][source] = {"exists": False, "name": name}
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
    radar = _latest_file(sdir, "radar_*.json")
    if radar:
        arts["radar_date"] = radar.stem.replace("radar_", "")
    quant = _latest_file(sdir, "quant_*.json")
    if quant:
        doc = _read_json(quant) or {}
        arts["quant"] = {
            "as_of": doc.get("as_of"),
            "rows": len(doc.get("rows") or []),
            "themes": len(doc.get("themes") or []),
        }
    try:
        from ptm.llm import setups_model

        arts["model"] = setups_model()
    except Exception:
        arts["model"] = ""
    ranking = _latest_file(data_dir("setups"), "setups_*.json")
    if ranking:
        doc = _read_json(ranking) or {}
        board = doc.get("leaderboard") or {}
        arts["ranking"] = {
            "as_of": doc.get("as_of"),
            "groups": len(doc.get("groups") or []),
            "ranked": sum(len(g.get("ranking") or []) for g in doc.get("groups") or []),
            "longs": len(board.get("longs") or []),
            "shorts": len(board.get("shorts") or []),
            "file": ranking.name,
        }
    ideadir = ideas_dir_setups()
    arts["reports"] = sum(1 for _ in ideadir.rglob("*.md")) if ideadir.exists() else 0
    return arts


def get_ranking() -> dict:
    """The latest group ranking + cross-industry leaderboard."""
    from ptm.config import data_dir

    path = _latest_file(data_dir("setups"), "setups_*.json")
    if not path:
        return {"error": "no ranking yet: run the radar, refresh fundamentals, then Rank industries"}
    return {"ranking": _read_json(path) or {}, "file": path.name}


def list_reports() -> dict:
    ideadir = ideas_dir_setups()
    reports = []
    if ideadir.exists():
        for path in sorted(ideadir.rglob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True):
            rel = str(path.relative_to(ideadir))
            reports.append({"path": rel, "mtime": time.strftime("%Y-%m-%d %H:%M", time.localtime(path.stat().st_mtime))})
    return {"reports": reports, "dir": str(ideadir)}


def read_report(rel: str) -> dict:
    ideadir = ideas_dir_setups().resolve()
    path = (ideadir / rel).resolve()
    if not str(path).startswith(str(ideadir)) or not path.is_file():
        return {"error": "not found"}
    return {"path": rel, "markdown": path.read_text(encoding="utf-8")}
