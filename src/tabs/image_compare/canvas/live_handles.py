"""Live Qt-object handles: the single shiboken lifetime mechanism.

Three call sites used to carry their own copy of the same guard
(``ui_update_batcher`` flush, toolbar availability/fanout, capture
quiet-setter): chrome rebuilds between store emits can delete the C++ side
while the Python wrapper stays referenced, so any C++ call raises
``RuntimeError: ... already deleted`` — once per emit (storm). This module
is the one place that asks shiboken; every site delegates here.

Fail-open by design: when shiboken is unavailable or undecided the handle
reports alive and the per-site ``try/except RuntimeError`` backstop still
catches the race. Skip-debug lines are throttled once per key (a dead
wrapper would otherwise spam once per emit until the next widget rebuild).

Phase P2 of plan-render-core-consolidation-2026-09-13.
"""

from __future__ import annotations

import logging
from typing import Any
from core.log_names import APP_LOGGER_NAME

logger = logging.getLogger(APP_LOGGER_NAME)

# Last logged skip key (throttle: one debug line per key, not per store
# emit — the guarded fanouts run on every emit and a dead wrapper would
# otherwise spam once per emit until the next widget rebuild).
_last_skip_sig: Any = None


def is_qt_alive(obj: Any) -> bool:
    """False when a PySide6 wrapper outlived its C++ object.

    Fail-open True when shiboken is unavailable or undecided — the
    per-site ``try/except RuntimeError`` still catches the race between
    this check and the guarded C++ call.
    """
    try:
        import shiboken6  # type: ignore
    except Exception:
        return True
    try:
        return bool(shiboken6.isValid(obj))
    except Exception:
        return True


def note_skipped_once(key: Any, message: str, *args: Any) -> None:
    """Debug-log a skip once per key; consecutive repeats stay silent."""
    global _last_skip_sig
    if _last_skip_sig != key:
        _last_skip_sig = key
        logger.debug(message, *args)


class LiveHandle:
    """Owns one Qt object reference; the only wrapper that asks shiboken.

    ``key`` identifies the control for the once-per-key skip throttle
    (e.g. the toolbar attr name); when omitted, each skip logs.
    """

    __slots__ = ("_obj", "key")

    def __init__(self, obj: Any, key: Any = None) -> None:
        self._obj = obj
        self.key = key if key is not None else obj

    @property
    def obj(self) -> Any:
        """The wrapped Qt object (may be C++-deleted — check first)."""
        return self._obj

    def is_alive(self) -> bool:
        """Single shiboken check — fail-open, see :func:`is_qt_alive`."""
        return is_qt_alive(self._obj)

    def note_skipped(self, message: str, *args: Any) -> None:
        """Throttled skip-debug for this handle's key."""
        note_skipped_once(self.key, message, *args)
