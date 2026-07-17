"""Session-state dataclasses owned by the image-compare tab.

Moved out of ``core.store_viewport`` on 2026-07-09. ``core.store_viewport
.SessionData`` no longer hardcodes a comparison-tab-specific default; its
bare-construction default is ``image_state=None, render_cache=None`` and
callers that need real comparison-tab session data go through
``core.store_viewport.create_session_data("image_compare")`` (which routes
to ``ImageCompareTab.create_default_session_data()``, defined in
``tabs/image_compare/tab.py``, which builds these dataclasses).

Any platform/plugin code that reads ``session_data.image_state`` /
``.render_cache`` must tolerate ``None`` for sessions that are not
``image_compare`` — see the guards in ``plugins/settings/manager.py``,
``plugins/settings/application_service.py``, and
``ui/managers/dialog_manager.py``.
"""

from __future__ import annotations

import copy
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Optional

from PIL import Image

from core.store_viewport import RenderConfig, SessionData

__all__ = [
    "ImageSessionState",
    "RenderCacheState",
    "RenderConfig",
    "SessionData",
]

@dataclass
class ImageSessionState:
    image1: Optional[Any] = None
    image2: Optional[Any] = None

    loaded_image1_paths: list[str] = field(default_factory=list)
    loaded_image2_paths: list[str] = field(default_factory=list)
    loaded_current_index1: int = -1
    loaded_current_index2: int = -1

    auto_calculate_psnr: bool = False
    auto_calculate_ssim: bool = False
    psnr_value: Optional[float] = None
    ssim_value: Optional[float] = None

    def clone(self):
        new_obj = copy.copy(self)
        new_obj.loaded_image1_paths = list(self.loaded_image1_paths)
        new_obj.loaded_image2_paths = list(self.loaded_image2_paths)
        return new_obj

@dataclass
class RenderCacheState:

    display_cache_image1: Optional[Image.Image] = None
    display_cache_image2: Optional[Image.Image] = None
    scaled_image1_for_display: Optional[Image.Image] = None
    scaled_image2_for_display: Optional[Image.Image] = None
    cached_scaled_image_dims: Optional[tuple[int, int]] = None
    last_display_cache_params: Optional[tuple] = None

    unified_image_cache: OrderedDict = field(default_factory=OrderedDict)
    unification_in_progress: bool = False
    pending_unification_paths: Optional[tuple[str, str]] = None

    caches: dict = field(default_factory=dict)
    feature_caches: dict = field(default_factory=dict)
    cached_split_base_image: Optional[Any] = None
    last_split_cached_params: Optional[tuple] = None
    cached_diff_image: Optional[Any] = None

    def clone(self):
        new_obj = copy.copy(self)
        new_obj.unified_image_cache = self.unified_image_cache.__class__(
            self.unified_image_cache
        )
        new_obj.caches = dict(self.caches)
        new_obj.feature_caches = dict(self.feature_caches)
        return new_obj
