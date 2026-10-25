"""Lightweight startup phase timing when IMGSLI_STARTUP_TRACE=1.

Two destinations, one vocabulary:

* :func:`startup_mark` -- the ordinary logger stream (BlinkTable.startup),
  visible in ``log.txt`` from the moment ``core.bootstrap`` configures logging;
* :func:`early_mark` -- the early file sink from :mod:`core.startup_early_log`,
  which exists *before* logging does (``main.entry``, the module imports,
  ``QApplication``, the RHI/D3D11 probe). Off unless a startup-diagnostics flag
  (``IMGSLI_STARTUP_TRACE`` / ``IMGSLI_STALL_WATCH``) is on.

Marks emitted through ``startup_mark`` before ``ctx.logging_ready`` were dropped
by an unconfigured logger; that is why the pre-window phases use
``early_mark`` even when no log handler exists yet.
"""

from __future__ import annotations

import logging
import time

from shared.debug_flags import env_flag as _env_flag
from core import startup_early_log
from core.log_names import APP_LOGGER_NAME

logger = logging.getLogger(f"{APP_LOGGER_NAME}.startup")

_origin: float | None = None
_last: float | None = None

#: Phase whose emission means the ordinary log now owns diagnostics.
_LOGGING_READY_PHASE = "ctx.logging_ready"


def is_startup_trace_enabled() -> bool:
    return _env_flag("IMGSLI_STARTUP_TRACE")


def startup_mark(phase: str) -> None:
    if phase == _LOGGING_READY_PHASE:
        # Not gated on IMGSLI_STARTUP_TRACE: the stall watchdog routes through
        # the early file until this phase fires, even when only its own flag is
        # set. ``core.bootstrap`` emits it once, after setup_logging().
        startup_early_log.mark_logging_ready()
    if not is_startup_trace_enabled():
        return
    global _origin, _last
    now = time.monotonic()
    if _origin is None:
        _origin = now
        _last = now
        logger.info("startup +%6.0fms  %s", 0.0, phase)
        return
    assert _last is not None and _origin is not None
    delta_ms = (now - _last) * 1000.0
    total_ms = (now - _origin) * 1000.0
    _last = now
    logger.info(
        "startup +%6.0fms (+%5.0fms)  %s",
        total_ms,
        delta_ms,
        phase,
    )


def early_mark(name: str, **fields: object) -> None:
    """Write one phase mark to the early startup file (no-op when it is off)."""
    startup_early_log.write_mark(name, **fields)


def early_log_path() -> str | None:
    """Path of the early startup file in use, or ``None`` when it is off."""
    try:
        return startup_early_log.path()
    except Exception:
        return None


def reset_startup_trace() -> None:
    """Clear the timing origin so a fresh startup can be measured in-process.

    Without this, ``_origin`` from a previous ``initialize()`` (or a test)
    leaks into the next run and every delta/total is measured against a
    stale clock. Primary use: tests and re-initialization.
    """
    global _origin, _last
    _origin = None
    _last = None
