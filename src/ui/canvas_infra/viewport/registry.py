from __future__ import annotations

from functools import lru_cache

from .contract import CanvasViewportFeature
from .zoom import VIEWPORT_FEATURE

@lru_cache(maxsize=1)
def get_canvas_viewport_features() -> tuple[CanvasViewportFeature, ...]:
    return (VIEWPORT_FEATURE,)
