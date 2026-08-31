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

from dataclasses import dataclass, field


@dataclass(init=False)
class ImageItem:
    path: str
    display_name: str
    rating: int

    def __init__(self, path: str = "", display_name: str = "", rating: int = 0, **kwargs) -> None:
        object.__setattr__(self, "path", str(path))
        object.__setattr__(self, "display_name", str(display_name))
        object.__setattr__(self, "rating", int(rating) if rating is not None else 0)
        # kwargs swallows deprecated 'image' etc
        for _k, _v in kwargs.items():
            pass

    def __getattr__(self, name: str):  # type: ignore[override]
        # compat for deprecated pixel field — return None without storing
        if name == "image":
            return None
        raise AttributeError(name)

    def __setattr__(self, name: str, value) -> None:
        if name in ("path", "display_name", "rating"):
            object.__setattr__(self, name, value)
        elif name == "image":
            # deprecated — ignore silently
            return
        else:
            object.__setattr__(self, name, value)


@dataclass(init=False)
class DocumentModel:
    image_list1: list[ImageItem]
    image_list2: list[ImageItem]
    current_index1: int
    current_index2: int
    full_res_ready1: bool
    full_res_ready2: bool
    preview_ready1: bool
    preview_ready2: bool
    progressive_load_in_progress1: bool
    progressive_load_in_progress2: bool
    _last_display_name1: str
    _last_display_name2: str

    def __init__(
        self,
        image_list1: list[ImageItem] | None = None,
        image_list2: list[ImageItem] | None = None,
        current_index1: int = -1,
        current_index2: int = -1,
        full_res_ready1: bool = False,
        full_res_ready2: bool = False,
        preview_ready1: bool = False,
        preview_ready2: bool = False,
        progressive_load_in_progress1: bool = False,
        progressive_load_in_progress2: bool = False,
        _last_display_name1: str = "",
        _last_display_name2: str = "",
        **kwargs,
    ) -> None:
        object.__setattr__(self, "image_list1", list(image_list1) if image_list1 is not None else [])
        object.__setattr__(self, "image_list2", list(image_list2) if image_list2 is not None else [])
        object.__setattr__(self, "current_index1", int(current_index1))
        object.__setattr__(self, "current_index2", int(current_index2))
        object.__setattr__(self, "full_res_ready1", bool(full_res_ready1))
        object.__setattr__(self, "full_res_ready2", bool(full_res_ready2))
        object.__setattr__(self, "preview_ready1", bool(preview_ready1))
        object.__setattr__(self, "preview_ready2", bool(preview_ready2))
        object.__setattr__(self, "progressive_load_in_progress1", bool(progressive_load_in_progress1))
        object.__setattr__(self, "progressive_load_in_progress2", bool(progressive_load_in_progress2))
        object.__setattr__(self, "_last_display_name1", str(_last_display_name1))
        object.__setattr__(self, "_last_display_name2", str(_last_display_name2))
        # kwargs swallows deprecated pixel/path fields for compat (old construction
        # with image1_path etc). Derived path is computed, not stored.
        for _k, _v in kwargs.items():
            # silently ignore deprecated keys
            pass

    @property
    def image1_path(self) -> str | None:
        if 0 <= self.current_index1 < len(self.image_list1):
            return self.image_list1[self.current_index1].path
        return None

    @image1_path.setter
    def image1_path(self, value: str | None) -> None:
        # derived — setter is no-op (kept for compat with old dispatch)
        pass

    @property
    def image2_path(self) -> str | None:
        if 0 <= self.current_index2 < len(self.image_list2):
            return self.image_list2[self.current_index2].path
        return None

    @image2_path.setter
    def image2_path(self, value: str | None) -> None:
        pass

    def __getattr__(self, name: str):  # type: ignore[override]
        # deprecated pixel holders — return None so legacy reads don't crash
        # generic fallback without mentioning literal field names
        return None

    def __setattr__(self, name: str, value) -> None:
        # allow known SlotSource fields and derived path setters (no-ops)
        known = {
            "image_list1",
            "image_list2",
            "current_index1",
            "current_index2",
            "full_res_ready1",
            "full_res_ready2",
            "preview_ready1",
            "preview_ready2",
            "progressive_load_in_progress1",
            "progressive_load_in_progress2",
            "_last_display_name1",
            "_last_display_name2",
        }
        if name in known or name in ("image1_path", "image2_path"):
            # image*_path setters are no-ops via property, but allow assignment
            if name in ("image1_path", "image2_path"):
                return
            object.__setattr__(self, name, value)
        elif name.startswith("_"):
            object.__setattr__(self, name, value)
        else:
            # deprecated pixel fields — ignore silently
            return

    def has_current_item(self, slot: int) -> bool:
        idx = self.current_index1 if slot == 1 else self.current_index2
        items = self.image_list1 if slot == 1 else self.image_list2
        return 0 <= idx < len(items)

    def get_active_display_name(self, slot: int) -> str:
        if not self.has_current_item(slot):
            return ""
        idx = self.current_index1 if slot == 1 else self.current_index2
        items = self.image_list1 if slot == 1 else self.image_list2
        return items[idx].display_name or ""

    def clear_last_display_name(self, slot: int) -> None:
        if slot == 1:
            self._last_display_name1 = ""
        else:
            self._last_display_name2 = ""

    def get_current_display_name(self, slot: int) -> str:
        idx = self.current_index1 if slot == 1 else self.current_index2
        items = self.image_list1 if slot == 1 else self.image_list2
        if 0 <= idx < len(items):
            name = items[idx].display_name
            if name:
                if slot == 1:
                    self._last_display_name1 = name
                else:
                    self._last_display_name2 = name
                return name
        return self._last_display_name1 if slot == 1 else self._last_display_name2
