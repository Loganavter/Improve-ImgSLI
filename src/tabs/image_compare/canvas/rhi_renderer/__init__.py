"""RHI canvas renderer — package init (thin, no implementation).

The renderer implementation lives in ``renderer.py`` (the
``RhiCanvasRenderer`` class); this module only re-exports the public
surface the rest of the app imports through the package.
"""

from ..texture_parts.tile_geometry import (
    _apron_rect,
    _TILE_APRON_PX,
    _viewport_zoom_offset_for_tile,
    _visible_side_image_rect,
)
from shared.rendering.tile_texture_service import _tile_indices_with_margin
from .renderer import RhiCanvasRenderer
from .residency import _TILE_CACHE_BUDGET_BYTES
from .resources import _ARRAY_LAYER_PX
from .uniforms import pack_base_uniforms

__all__ = [
    "RhiCanvasRenderer",
    "pack_base_uniforms",
    "_apron_rect",
    "_ARRAY_LAYER_PX",
    "_TILE_APRON_PX",
    "_TILE_CACHE_BUDGET_BYTES",
    "_tile_indices_with_margin",
    "_viewport_zoom_offset_for_tile",
    "_visible_side_image_rect",
]
