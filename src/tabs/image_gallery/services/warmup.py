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

The warm-up follows the DURABLE judgment domain (owner 2026-10-27): on the
``ai`` domain nothing on the cards is read through the local stack, so paying
(or even scheduling) the torch import there is cost for work the user is not
looking at. ``schedule_warmup`` therefore skips on ``ai`` WITHOUT consuming the
process-once flag, and the domain switch to Algorithms warms for real.

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
#: Reader of the gallery's DURABLE judgment domain, installed by the tab
#: (``GalleryController._judgment_domain``). ``None`` = nobody can say, which
#: keeps the historical "warm on open" behaviour.
_domain_provider = None


def set_domain_provider(provider) -> None:
    """Install the durable-domain reader (the tab wires its controller here).

    One field, one reader: the warm-up must never guess the domain from the
    widget tree or from a view preference it cannot see.
    """
    global _domain_provider
    _domain_provider = provider


def durable_domain() -> str:
    """The durable judgment domain (``""`` when no provider can answer)."""
    provider = _domain_provider
    if provider is None:
        return ""
    try:
        return str(provider() or "").strip().lower()
    except Exception:
        return ""


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


def schedule_warmup(reason: str = "tab-open", *, domain: str | None = None) -> bool:
    """Start the warm-up once per process (no-op afterwards). Returns started.

    ``domain`` is the durable judgment domain; ``None`` asks the provider the
    tab installed. Only Algorithms needs the local stack: on ``ai`` this is a
    no-op that does NOT consume the process-once flag, so the later switch to
    Algorithms still warms the stack the first time the user is about to see
    detector numbers.
    """
    global _started
    if _disabled():
        return False
    # The domain vocabulary is the one ``services.quality_read`` defines (never a
    # second spelling of "ai"): the warm-up reads the same token the read path
    # does, and a provider that cannot answer ("" / None) keeps the historical
    # Algorithms behaviour.
    from tabs.image_gallery.services.quality_read import AI_DOMAIN, normalize_domain

    try:
        live = normalize_domain(domain) if domain is not None else normalize_domain(durable_domain())
    except Exception:
        live = ""
    if live == AI_DOMAIN:
        logger.debug(
            "warmup: not scheduled (%s) — the ai domain reads no local numbers", reason
        )
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


__all__ = [
    "durable_domain",
    "reset_for_tests",
    "schedule_warmup",
    "set_domain_provider",
    "warm_local_backends",
]
