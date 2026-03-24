from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

@dataclass
class ImageItem:
    image: Optional[Any] = None
    path: str = ""
    display_name: str = ""
    rating: int = 0

@dataclass
class DocumentModel:
    image_list1: list[ImageItem] = field(default_factory=list)
    image_list2: list[ImageItem] = field(default_factory=list)
    current_index1: int = -1
    current_index2: int = -1
    original_image1: Optional[Any] = None
    original_image2: Optional[Any] = None
    full_res_image1: Optional[Any] = None
    full_res_image2: Optional[Any] = None
    image1_path: Optional[str] = None
    image2_path: Optional[str] = None
    preview_image1: Optional[Any] = None
    preview_image2: Optional[Any] = None
    full_res_ready1: bool = False
    full_res_ready2: bool = False
    preview_ready1: bool = False
    preview_ready2: bool = False
    progressive_load_in_progress1: bool = False
    progressive_load_in_progress2: bool = False

    def get_current_display_name(self, slot: int) -> str:
        idx = self.current_index1 if slot == 1 else self.current_index2
        items = self.image_list1 if slot == 1 else self.image_list2
        if 0 <= idx < len(items):
            return items[idx].display_name
        return ""
