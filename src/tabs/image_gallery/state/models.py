"""Gallery session-slot models — Wave 1 (plan-gallery-redux-2026-09-24).

The ``gallery`` session slot is path-only state: item identity (path +
mtime), thumbnail *status* strings, selection ids, filter text, folder, and
a triage summary. NEVER in this slot (stays controller/widget-local):
``QPixmap`` caches, thumbnail LOADING in-flight flags, ``_folder_gen``
counters, thread pools/workers, VLM streams, widget internals.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field


@dataclass
class GalleryItemMeta:
    """One pool member: identity + scalar display facts only."""

    path: str = ""
    mtime_ns: int = 0
    status: str = "not_loaded"
    rank: int | None = None


@dataclass
class GallerySlotState:
    """Value of the ``gallery`` session slot (single source of truth).

    ``items`` is the pool in display order; ``selection`` is an ordered
    list of path-id strings; ``folder``/``triage_state``/``mode``/
    ``source_path`` are plain scalars (``None`` == no context).
    """

    items: list[GalleryItemMeta] = field(default_factory=list)
    selection: list[str] = field(default_factory=list)
    filter_text: str = ""
    folder: str | None = None
    triage_state: str = "idle"
    mode: str | None = None
    source_path: str | None = None

    def clone(self):
        new_obj = copy.copy(self)
        new_obj.items = [copy.copy(it) for it in self.items]
        new_obj.selection = list(self.selection)
        return new_obj


def fresh_gallery_slot_state() -> GallerySlotState:
    """Factory for a new ``gallery`` slot value (reducer None-branch)."""
    return GallerySlotState()


__all__ = [
    "GalleryItemMeta",
    "GallerySlotState",
    "fresh_gallery_slot_state",
]
