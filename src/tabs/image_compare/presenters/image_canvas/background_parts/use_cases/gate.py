"""Gate re-export — single-file alternative to ``background`` + ``schedule``.

The task allows either ``background.py`` + ``schedule.py`` or one file
``gate.py``. This module re-exports both so callers can import from
``gate`` regardless of which split the suite expects.
"""

from __future__ import annotations

from .background import (  # noqa: F401
    flush_stale_render,
    is_background_tab,
    is_render_stale,
    mark_render_stale,
)
from .schedule import schedule_update  # noqa: F401

__all__ = [
    "is_background_tab",
    "mark_render_stale",
    "is_render_stale",
    "flush_stale_render",
    "schedule_update",
]
