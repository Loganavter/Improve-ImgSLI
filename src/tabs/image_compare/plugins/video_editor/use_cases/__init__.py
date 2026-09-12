"""Thin-owner use_cases for video_editor.

See docs/dev/CODE_PATTERNS.md — thin owner + use_cases/.
Presenter / coordinators own state + wiring; plain functions here hold the
domain logic and take the owner as first arg.
"""

from .initialization import initialize_editor_from_snapshots
from .bounds import recalculate_global_bounds, on_global_bounds_calculated

__all__ = [
    "initialize_editor_from_snapshots",
    "recalculate_global_bounds",
    "on_global_bounds_calculated",
]
