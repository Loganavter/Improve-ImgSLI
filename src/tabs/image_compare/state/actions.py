"""PipelineCache actions — Bucket C (plan_render_dispatch_and_gap_fix.md Phase 3).

All pixel/preview/unify puts go through these actions via ``store.transact``
so ``Dispatcher`` single-alloc + single emit replaces 6-10 direct
``pl.cache.put_*`` paths (slot.py, image_decode.py). The reducer lives in
``reducers.py:PipelineCacheReducer`` and the slot is ``pipeline``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.state_management.action_base import Action, ActionType


@dataclass
class PutPixelAction(Action):
    path: str
    store: Any
    crop_service: Any = None
    auto_crop: bool | None = None

    def __init__(self, path: str, store: Any, crop_service: Any = None, auto_crop: bool | None = None):
        super().__init__(type=ActionType.PIPELINE_PUT_PIXEL)
        self.path = str(path)
        self.store = store
        self.crop_service = crop_service
        self.auto_crop = auto_crop

    def get_payload(self) -> dict[str, Any]:
        return {"path": self.path, "store": getattr(self.store, "uid", id(self.store)), "auto_crop": self.auto_crop}


@dataclass
class PutPreviewAction(Action):
    path: str
    qimage: Any
    crop_service: Any = None
    auto_crop: bool | None = None

    def __init__(self, path: str, qimage: Any, crop_service: Any = None, auto_crop: bool | None = None):
        super().__init__(type=ActionType.PIPELINE_PUT_PREVIEW)
        self.path = str(path)
        self.qimage = qimage
        self.crop_service = crop_service
        self.auto_crop = auto_crop

    def get_payload(self) -> dict[str, Any]:
        return {"path": self.path, "auto_crop": self.auto_crop}


@dataclass
class PutUnifiedAction(Action):
    uid1: Any
    uid2: Any
    method: str
    w: int
    h: int
    pair: Any

    def __init__(self, uid1: Any, uid2: Any, method: str, w: int, h: int, pair: Any):
        super().__init__(type=ActionType.PIPELINE_PUT_UNIFIED)
        self.uid1 = uid1
        self.uid2 = uid2
        self.method = str(method)
        self.w = int(w)
        self.h = int(h)
        self.pair = pair

    def get_payload(self) -> dict[str, Any]:
        return {"uid1": self.uid1, "uid2": self.uid2, "method": self.method, "w": self.w, "h": self.h}


@dataclass
class EvictPipelineAction(Action):
    path: str

    def __init__(self, path: str):
        super().__init__(type=ActionType.PIPELINE_EVICT)
        self.path = str(path)

    def get_payload(self) -> dict[str, Any]:
        return {"path": self.path}
