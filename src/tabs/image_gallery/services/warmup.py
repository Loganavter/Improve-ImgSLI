"""One-time background warm-up of the LOCAL detection stack at tab open.

Owner report 2026-10-22 ("долгая заминка перед анализом"): the first folder's
Stage-2 pass pays a ~3.1 s first-use import/build of the learned quality backend
(``learned quality backend ready (piq)`` in the log) INSIDE the analysis window,
so the user waits before any card is read. The decode stack (pyvips/PIL) pays a
smaller first-use import too.

This module loads the same process singletons the pass uses, once, from a daemon
thread scheduled on the gallery tab's first activation. It does not change the
import discipline's hazard — torch already runs in this process for the first
analysis, and ``quality_models`` guards its singletons with a lock — it only
moves the cost off the critical path (the user is looking at the tab, not at a
half-analyzed folder).

Kill-switch: ``IMGSLI_GALLERY_NO_WARMUP=1`` (a host with a tiny CPU can keep the
old lazy behaviour). Never raises; never touches Qt from the thread.
"""

from __future__ import annotations

import logging
import threading
import time
from core.log_names import APP_LOGGER_NAME
from shared.debug_flags import env_value as _env_value

logger = logging.getLogger(APP_LOGGER_NAME)

#: Set once the warm-up thread has been started in this process.
_started = False
_lock = threading.Lock()


def _disabled() -> bool:
    try:
        value = _env_value("IMGSLI_GALLERY_NO_WARMUP", "")
        return str(value).strip().lower() in ("1", "true", "yes", "on")
    except Exception:
        return False


def warm_local_backends() -> dict:
    """Load the first-use singletons of the local pass. Blocking; worker only.

    Returns an honest report ``{"learned": status, "decode": bool, "ms": n}`` —
    the diagnostics line the log carries so the pause can be attributed.
    """
    t0 = time.perf_counter()
    report: dict = {"learned": None, "decode": False, "ms": 0}
    try:
        from tabs.image_gallery.services import quality_models

        report["learned"] = quality_models.backend_status()
    except Exception:
        logger.debug("warmup: learned backend load failed", exc_info=True)
    try:
        import pyvips  # noqa: F401  (libvips init happens on first import)

        from PIL import Image  # noqa: F401

        report["decode"] = True
    except Exception:
        logger.debug("warmup: decode stack import failed", exc_info=True)
    report["ms"] = int((time.perf_counter() - t0) * 1000)
    try:
        from tabs.image_gallery.debug import gallery_debug as _dbg

        _dbg(
            "warmup: local backends ready learned=%s decode=%s in %d ms (off the analysis path)",
            report["learned"],
            report["decode"],
            report["ms"],
        )
    except Exception:
        pass
    return report


def schedule_warmup(*, reason: str = "tab-open") -> bool:
    """Start the warm-up once per process (no-op afterwards). Returns started."""
    global _started
    if _disabled():
        return False
    with _lock:
        if _started:
            return False
        _started = True
    try:
        thread = threading.Thread(
            target=warm_local_backends,
            name="gallery-backend-warmup",
            daemon=True,
        )
        thread.start()
        logger.debug("warmup: started (%s)", reason)
        return True
    except Exception:
        logger.debug("warmup: thread start failed", exc_info=True)
        return False


def reset_for_tests() -> None:
    """Test hook: forget the process-once flag."""
    global _started
    with _lock:
        _started = False


__all__ = ["reset_for_tests", "schedule_warmup", "warm_local_backends"]
