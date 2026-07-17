"""Image-compare document state.

Owns the image-pair document model (``image_list1/2``, ``current_index1/2``,
``original_image1/2``, ``full_res_image1/2``, ``preview_image1/2``,
``image1_path/image2_path`` and load-state flags).

Tier contract (see ``docs/dev/rendering/tile-rendering-system.md``):

- ``full_res_image*`` — ``TiledPixelStore`` (memmap full-res tier)
- ``preview_image*`` — ``PIL.Image`` only (bounded progressive preview, ≤1024 px)
- ``original_image*`` — ``PIL.Image`` (legacy/small paste paths)

Preview fields must never hold ``TiledPixelStore``; load workers set
``is_preview=True`` and skip ``maybe_wrap_pixel_store``.

This module is the authoritative location for ``DocumentModel`` and
``ImageItem`` (see step 8 of ``docs/dev/TAB_OWNERSHIP_AUDIT.md``). The
"document" session state slot is registered by this tab's
``SessionBlueprint`` (``tabs/image_compare/plugin.py``); platform code
reaches it via ``store.get_session_state_slot("document")``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from PIL import Image

if TYPE_CHECKING:
    from shared.image_processing.tiled_pixel_store import TiledPixelStore


@dataclass
class ImageItem:
    image: Optional["TiledPixelStore | Image.Image"] = None
    path: str = ""
    display_name: str = ""
    rating: int = 0


@dataclass
class DocumentModel:
    image_list1: list[ImageItem] = field(default_factory=list)
    image_list2: list[ImageItem] = field(default_factory=list)
    current_index1: int = -1
    current_index2: int = -1
    original_image1: Optional[Image.Image] = None
    original_image2: Optional[Image.Image] = None
    full_res_image1: Optional["TiledPixelStore"] = None
    full_res_image2: Optional["TiledPixelStore"] = None
    image1_path: Optional[str] = None
    image2_path: Optional[str] = None
    preview_image1: Optional[Image.Image] = None
    preview_image2: Optional[Image.Image] = None
    full_res_ready1: bool = False
    full_res_ready2: bool = False
    preview_ready1: bool = False
    preview_ready2: bool = False
    progressive_load_in_progress1: bool = False
    progressive_load_in_progress2: bool = False
    _last_display_name1: str = ""
    _last_display_name2: str = ""

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
