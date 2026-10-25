"""Warm heavy lazy imports off the GUI thread.

Measured on the D3D11 host (2026-10-24, GUI stall watchdog): the first use of
Image Compare's analysis path blocked the GUI thread for **1350 ms** importing
``scipy.stats``/``skimage.metrics``, and a later toolbar paint blocked **320 ms**
on importing a magnifier module whose PySide feature check walks
``inspect.getsource``. Neither import is needed *at* that moment -- the modules
are needed one interaction earlier than they are first touched.

This module imports a fixed list of heavy third-party modules in a daemon
thread shortly after startup, so the cost lands while the UI is still coming up
instead of freezing a paint. It never raises, never imports tab code (``core``
must not depend on ``tabs``), and is skipped with ``IMGSLI_IMPORT_WARMUP=0``.
"""

from __future__ import annotations

import importlib
import logging
import sys
import threading
from core.log_names import APP_LOGGER_NAME
from shared.debug_flags import env_value as _env_value

logger = logging.getLogger(f"{APP_LOGGER_NAME}.import_warmup")

#: Third-party modules whose first import is expensive and whose use is
#: foreseeable (analysis metrics). Tab-owned modules are warmed by their tab.
DEFAULT_MODULES: tuple[str, ...] = (
    "scipy.stats",
    "skimage.metrics",
    "skimage.feature",
    "skimage.util",
)


def enabled() -> bool:
    return (_env_value("IMGSLI_IMPORT_WARMUP", "") or "").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def _import_all(modules: tuple[str, ...]) -> None:
    for name in modules:
        try:
            importlib.import_module(name)
        except Exception as exc:  # optional dependency or platform quirk
            logger.debug("import warm-up skipped %s: %s", name, exc)


def start(modules: tuple[str, ...] | None = None) -> threading.Thread | None:
    """Start the warm-up thread; returns it (or None when disabled/frozen off).

    Idempotent per process: a second call returns None (the modules are either
    imported or being imported already).
    """
    if not enabled():
        return None
    if getattr(start, "_started", False):
        return None
    names = tuple(modules) if modules is not None else DEFAULT_MODULES
    if not names:
        return None
    thread = threading.Thread(
        target=_import_all,
        args=(names,),
        name="import-warmup",
        daemon=True,
    )
    thread.start()
    start._started = True  # type: ignore[attr-defined]
    logger.debug("import warm-up started for %s", ", ".join(names))
    return thread


def pending(modules: tuple[str, ...] | None = None) -> tuple[str, ...]:
    """Modules from the list that are not imported yet (diagnostics/tests)."""
    names = tuple(modules) if modules is not None else DEFAULT_MODULES
    return tuple(name for name in names if name not in sys.modules)
