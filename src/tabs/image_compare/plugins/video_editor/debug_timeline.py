"""Single throttled debug channel for video timeline.

Replaces ~40 ad-hoc video debug / thumbnail debug / DBG calls with
one throttled logger ``ImproveImgSLI.video_timeline`` + Tracer.

Gated by IMGSLI_VIDEO_EDITOR_DEBUG / IMGSLI_TIMELINE_DEBUG (per-zone
LOGGING.md:64). Throttle 700 ms per kind so resize/hover spam does not
flood log.txt. Payload goes to Tracer when IMGSLI_TRACE=1.

Contract: rg for legacy debug markers outside this file and tracing is 0.
"""

from __future__ import annotations

import logging
import time

from shared.debug_flags import env_flag

_thlog = logging.getLogger("ImproveImgSLI.video_timeline")
_last_emit_ms: dict[str, float] = {}
_INTERVAL_MS = 700.0


def _enabled() -> bool:
    return env_flag("IMGSLI_VIDEO_EDITOR_DEBUG") or env_flag("IMGSLI_TIMELINE_DEBUG") or env_flag("IMGSLI_IC_VIDEO_DEBUG")


def _should_emit(kind: str) -> bool:
    now_ms = time.monotonic() * 1000.0
    last = _last_emit_ms.get(kind, 0.0)
    if now_ms - last < _INTERVAL_MS:
        return False
    _last_emit_ms[kind] = now_ms
    return True
