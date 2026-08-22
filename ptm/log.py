from __future__ import annotations

import sys
import time
from datetime import datetime, timedelta


def log(message: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {message}", file=sys.stderr, flush=True)


def elapsed_since(started: float) -> str:
    return str(timedelta(seconds=int(max(0, time.monotonic() - started))))


def eta(done: int, total: int, started: float) -> str:
    if done <= 0 or total <= 0:
        return "?"
    remain = (time.monotonic() - started) / done * (total - done)
    return str(timedelta(seconds=int(max(0, remain))))
