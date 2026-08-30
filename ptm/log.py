from __future__ import annotations

import sys
import time
from datetime import datetime, timedelta
from threading import Lock

# Registered sinks receive every log line (e.g. the viewer's pipeline runner
# streams progress from them). Calls are best-effort: a sink raising must
# never break the pipeline that is logging.
_SINKS: list = []
_SINK_LOCK = Lock()


def add_sink(fn) -> None:
    """Register a callable(message: str) that receives every log line."""
    with _SINK_LOCK:
        if fn not in _SINKS:
            _SINKS.append(fn)


def remove_sink(fn) -> None:
    with _SINK_LOCK:
        if fn in _SINKS:
            _SINKS.remove(fn)


def log(message: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {message}"
    print(line, file=sys.stderr, flush=True)
    with _SINK_LOCK:
        sinks = list(_SINKS)
    for fn in sinks:
        try:
            fn(line)
        except Exception:
            pass


def elapsed_since(started: float) -> str:
    return str(timedelta(seconds=int(max(0, time.monotonic() - started))))


def eta(done: int, total: int, started: float) -> str:
    if done <= 0 or total <= 0:
        return "?"
    remain = (time.monotonic() - started) / done * (total - done)
    return str(timedelta(seconds=int(max(0, remain))))