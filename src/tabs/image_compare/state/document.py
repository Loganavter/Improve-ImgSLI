"""Image-compare document state — SlotSource only.

Owns the image-pair SlotSource (image_list1/2 + current_index1/2 +
derived image1_path/2). Pixels live in PipelineCache / viewport
image_state (PipelineView), not here. This is Phase 3 slim of
plan_loading_simplification.md — 7 fields/slot collapsed to
list+index+derived path.

This module is the authoritative location for DocumentModel and
ImageItem. The "document" session state slot is registered by this
tab's SessionBlueprint (tabs/image_compare/plugin.py); platform code
reaches it via store.get_session_state_slot("document").
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class ImageItem:
    path: str = ""
    display_name: str = ""
    rating: int = 0
    # Per-image autocrop override (W5): None == Auto (follow the global
    # auto_crop_black_borders setting), True == force on, False == force
    # off. Field declaration ONLY — all writes go through
    # SetCropOverrideAction + DocumentReducer (dataclasses.replace).
    # Plain bool|None stays JSON/YAML-serializable for persistence.
    crop_override: bool | None = None


def display_name_or_fallback(item) -> str:
    """Non-empty display name or basename(path) without extension, else "-----"."""
    name = getattr(item, "display_name", "") or ""
    if isinstance(name, str) and name.strip():
        return name
    path = getattr(item, "path", "") or ""
    if isinstance(path, str) and path:
        stem = os.path.splitext(os.path.basename(path))[0]
        if isinstance(stem, str) and stem.strip(" ."):
            return stem
    return "-----"


@dataclass
class DocumentModel:
    image_list1: list[ImageItem] = field(default_factory=list)
    image_list2: list[ImageItem] = field(default_factory=list)
    current_index1: int = -1
    current_index2: int = -1
    full_res_ready1: bool = False
    full_res_ready2: bool = False
    preview_ready1: bool = False
    preview_ready2: bool = False
    progressive_load_in_progress1: bool = False
    progressive_load_in_progress2: bool = False
    _last_display_name1: str = ""
    _last_display_name2: str = ""

    @property
    def image1_path(self) -> str | None:
        if 0 <= self.current_index1 < len(self.image_list1):
            return self.image_list1[self.current_index1].path
        return None

    @property
    def image2_path(self) -> str | None:
        if 0 <= self.current_index2 < len(self.image_list2):
            return self.image_list2[self.current_index2].path
        return None

    def has_current_item(self, slot: int) -> bool:
        idx = self.current_index1 if slot == 1 else self.current_index2
        items = self.image_list1 if slot == 1 else self.image_list2
        return 0 <= idx < len(items)

    def get_active_display_name(self, slot: int) -> str:
        if not self.has_current_item(slot):
            return ""
        idx = self.current_index1 if slot == 1 else self.current_index2
        items = self.image_list1 if slot == 1 else self.image_list2
        return display_name_or_fallback(items[idx])

    def clear_last_display_name(self, slot: int) -> None:
        if slot == 1:
            self._last_display_name1 = ""
        else:
            self._last_display_name2 = ""

    def get_current_display_name(self, slot: int) -> str:
        idx = self.current_index1 if slot == 1 else self.current_index2
        items = self.image_list1 if slot == 1 else self.image_list2
        if 0 <= idx < len(items):
            name = display_name_or_fallback(items[idx])
            if slot == 1:
                self._last_display_name1 = name
            else:
                self._last_display_name2 = name
            return name
        return self._last_display_name1 if slot == 1 else self._last_display_name2
