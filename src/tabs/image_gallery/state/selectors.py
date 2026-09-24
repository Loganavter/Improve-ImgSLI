"""Pure read helpers over ``GallerySlotState`` — Wave 1.

No Qt, no store access, never raises on ``None``/foreign state (returns
defaults). Write path is ``dispatcher.dispatch(...)`` only — never mutate
what these helpers return.
"""

from __future__ import annotations

from typing import Any

from tabs.image_gallery.state.models import GalleryItemMeta, GallerySlotState


def get_items(state: Any) -> list[GalleryItemMeta]:
    if isinstance(state, GallerySlotState):
        return list(state.items)
    return []


def get_item_paths(state: Any) -> list[str]:
    return [it.path for it in get_items(state)]


def get_item_by_path(state: Any, path: Any) -> GalleryItemMeta | None:
    try:
        key = str(path)
    except Exception:
        return None
    for it in get_items(state):
        if it.path == key:
            return it
    return None


def get_selection(state: Any) -> list[str]:
    if isinstance(state, GallerySlotState):
        return list(state.selection)
    return []


def get_selected_items(state: Any) -> list[GalleryItemMeta]:
    selected = set(get_selection(state))
    return [it for it in get_items(state) if it.path in selected]


def get_filter_text(state: Any) -> str:
    if isinstance(state, GallerySlotState):
        return state.filter_text
    return ""


def get_folder(state: Any) -> str | None:
    if isinstance(state, GallerySlotState):
        return state.folder
    return None


def get_triage_summary(state: Any) -> dict[str, Any]:
    """Triage summary scalars (state/mode/source + ranked count)."""
    if not isinstance(state, GallerySlotState):
        return {"triage_state": "idle", "mode": None, "source_path": None, "ranked": 0}
    return {
        "triage_state": state.triage_state,
        "mode": state.mode,
        "source_path": state.source_path,
        "ranked": sum(1 for it in state.items if it.rank is not None),
    }


__all__ = [
    "get_items",
    "get_item_paths",
    "get_item_by_path",
    "get_selection",
    "get_selected_items",
    "get_filter_text",
    "get_folder",
    "get_triage_summary",
]
