"""Public and internal data shapes for snapshot frame rendering."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class PreparedCanvasFrame:
    store: object
    plan: object
    output_width: int
    output_height: int
    image_dest_x: int
    image_dest_y: int
    fill_rgba: tuple[int, int, int, int]
    debug: dict


@dataclass(slots=True)
class ImagePrepCacheEntry:
    """Cached image-prep payload reused across consecutive similar frames."""

    display_img1: Any
    display_img2: Any
    source_img1: Any
    source_img2: Any
    source_key: Any
    display_cache_key: Any
    scaled_source1: Any
    scaled_source2: Any
    canvas_geometry: Any
    output_layout: Any
    target_size: tuple[int, int]
    content_size: tuple[int, int]
    pad_left: int
    pad_top: int
    render_w: int
    render_h: int
