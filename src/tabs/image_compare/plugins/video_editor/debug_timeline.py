"""Single throttled debug channel for video timeline.

Replaces ~40 ad-hoc video debug / thumbnail debug / DBG calls with
one throttled logger ``ImproveImgSLI.video_timeline`` + Tracer.

Timeline-zone gate is :func:`timeline_debug_enabled` below
(``IMGSLI_VIDEO_EDITOR_DEBUG`` / ``IMGSLI_TIMELINE_DEBUG``, permissive
``env_flag`` parsing per LOGGING.md:64). Throttle 700 ms per kind so
resize/hover spam does not flood log.txt. Payload goes to Tracer when
IMGSLI_TRACE=1.

Zone note (host-dbgflags epic): the ``IMGSLI_VIDEO_EDITOR_DEBUG``
umbrella disjunct is retained here by design — the full OR-split of
the video-family flags is a deferred supervisor phase and the
``enabled()`` predicates in ``tabs/image_compare/debug.py`` are
frozen. Narrowing happens per call site (this module's timeline-zone
gate vs the editor-zone ``ic_video_debug_enabled``), never by
dropping a disjunct from a shared predicate.

Contract: rg for legacy debug markers outside this file and tracing is 0.
"""

from __future__ import annotations

import logging
import time

from shared.debug_flags import env_flag

_thlog = logging.getLogger("ImproveImgSLI.video_timeline")
_last_emit_ms: dict[str, float] = {}
_INTERVAL_MS = 700.0


def timeline_debug_enabled() -> bool:
    """Timeline-zone gate: layout/scroll-area diagnostics.

    Canonical gate for timeline-zone call sites (e.g. the dialog
    shell's ``create_timeline_scroll_area`` log). Keeps the
    ``IMGSLI_VIDEO_EDITOR_DEBUG`` umbrella disjunct — narrowing to
    ``IMGSLI_TIMELINE_DEBUG``-only is deferred (would silence the site
    under the umbrella flag alone).
    """
    return env_flag("IMGSLI_VIDEO_EDITOR_DEBUG") or env_flag("IMGSLI_TIMELINE_DEBUG")


def _enabled() -> bool:
    # Compat alias: timeline zone has no third flag; the IC_VIDEO
    # disjunct some legacy sites carried is covered by the editor-zone
    # gate (ic_video_debug_enabled) at those sites, not here.
    return timeline_debug_enabled() or env_flag("IMGSLI_IC_VIDEO_DEBUG")


def _should_emit(kind: str) -> bool:
    now_ms = time.monotonic() * 1000.0
    last = _last_emit_ms.get(kind, 0.0)
    if now_ms - last < _INTERVAL_MS:
        return False
    _last_emit_ms[kind] = now_ms
    return True
