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

from core.store_viewport import RenderConfig, SessionData

__all__ = [
    "ImageSessionState",
    "PipelineCacheState",
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

    unification_in_progress: bool = False
    pending_unification_paths: Optional[tuple[str, str]] = None

    cached_diff_image: Optional[Any] = None
    # request_key (diff_mode, image_uid(source1), image_uid(source2), size1,
    # size2) cached_diff_image was computed for -- see diff_cache.py's
    # request_cached_diff_image_async, which compares this against the
    # live sources' own key to decide whether a recompute is needed,
    # instead of gating on cached_diff_image being None. Keeping the stale
    # image in place (rather than clearing it to None on every image swap)
    # lets the canvas keep showing the previous diff until the new one is
    # ready, instead of a diff-vanishes/plain-image/diff-reappears flash
    # (docs/dev/KNOWN_BUGS.md same-slot-swap SSIM follow-up).
    cached_diff_source_key: Optional[Any] = None

    def clone(self):
        return copy.copy(self)


@dataclass
class PipelineCacheState:
    """Store slot for PipelineCache — Bucket C (plan_render_dispatch_and_gap_fix.md).

    Holds the three LRU tiers as frozen copies. Reducer owns lifecycle
    (max 8 each) and ``close_pixel_store`` defer, not direct ``cache.put_*``.
    ``ImagePipeline.peek`` reads from this slot when a Store is present
    (falls back to the legacy ``PipelineCache`` for headless tests).
    """

    pixel: Any = field(default_factory=OrderedDict)
    preview: Any = field(default_factory=OrderedDict)
    unify: Any = field(default_factory=OrderedDict)

    max_pixel: int = 8
    max_preview: int = 8
    max_unify: int = 8

    def clone(self):
        new_obj = copy.copy(self)
        new_obj.pixel = OrderedDict(self.pixel)
        new_obj.preview = OrderedDict(self.preview)
        new_obj.unify = OrderedDict(self.unify)
        return new_obj
