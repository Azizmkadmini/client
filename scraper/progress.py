from __future__ import annotations

import json
import sys
from collections.abc import Callable
from typing import Any

_emit: Callable[[dict[str, Any]], None] | None = None


def set_progress_emitter(fn: Callable[[dict[str, Any]], None] | None) -> None:
    global _emit
    _emit = fn


def scraper_progress(*, fraction: float, message: str = "", phase: str = "") -> None:
    if _emit is None:
        return
    payload: dict[str, Any] = {
        "fraction": min(1.0, max(0.0, float(fraction))),
        "message": message,
        "phase": phase,
    }
    _emit(payload)


def stderr_json_progress_emitter(payload: dict[str, Any]) -> None:
    line = "SCRAPER_PROGRESS:" + json.dumps(payload, ensure_ascii=False)
    print(line, file=sys.stderr, flush=True)
