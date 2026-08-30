"""ImagePipeline — demand-driven decode → unify → lod pipeline.

Phase 1: thin wrapper around existing load_pixel_store + unify_pair with memo.
Phase 2 will wire ensure() into a single Store.transact.

For now the controller still calls loading.py; pipeline is opt-in via
controller.pipeline (constructed in _session_controller.py Phase 5).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import logging

from tabs.image_compare.pipeline.abort import AbortSignal
from tabs.image_compare.pipeline.cache import PipelineCache

logger = logging.getLogger("ImproveImgSLI")

if TYPE_CHECKING:
    from shared.image_processing.tiled_pixel_store import TiledPixelStore


@dataclass(frozen=True)
class PipelineView:
    """Read-only view published to Store (image_state.image1/2 + pyramid handles)."""

    image1: object | None
    image2: object | None
    path1: str | None
    path2: str | None
    unified: bool = False


class ImagePipeline:
    """Demand-driven pipeline. Single-flight via caller-provided AbortSignal."""

    def __init__(self, cache: PipelineCache | None = None):
        self.cache = cache or PipelineCache()
        # in-flight key -> AbortSignal (single-flight dedup)
        self._inflight: dict[tuple, AbortSignal] = {}

    # -- sync peek (no decode) --

    def peek(self, path: str, auto_crop: bool = True):
        return self.cache.get_pixel(path, auto_crop)

    # -- ensure tiers --

    def ensure_pixel(self, path: str, auto_crop: bool = True, signal: AbortSignal | None = None):
        if signal is not None and signal.is_aborted():
            return None
        cached = self.cache.get_pixel(path, auto_crop)
        if cached is not None:
            return cached
        # single-flight: if same path already loading, return None and let
        # caller await the in-flight result via controller's worker.
        # Phase 2 will add awaitable future; for now just load.
        try:
            store = self.cache.get_or_load(path, auto_crop=auto_crop)
            return store
        except Exception as e:
            logger.error(f"Pipeline ensure_pixel failed for {path}: {e}", exc_info=True)
            return None

    def ensure_unified(
        self,
        store1,
        store2,
        path1: str,
        path2: str,
        method: str,
        signal: AbortSignal | None = None,
    ):
        if store1 is None or store2 is None:
            return None, None
        if signal is not None and signal.is_aborted():
            return None, None
        # uid-based memo (store identity, not path, to catch re-decodes)
        uid1 = getattr(store1, "uid", None) or id(store1)
        uid2 = getattr(store2, "uid", None) or id(store2)
        # target size is max(cropped) inside unify_pair; we approximate via store size
        try:
            w1, h1 = int(getattr(store1, "width", 0) or 0), int(getattr(store1, "height", 0) or 0)
            w2, h2 = int(getattr(store2, "width", 0) or 0), int(getattr(store2, "height", 0) or 0)
            w, h = max(w1, w2), max(h1, h2)
        except Exception:
            w, h = 0, 0
        cached = self.cache.get_unified(uid1, uid2, method, w, h)
        if cached is not None:
            return cached
        try:
            from shared.image_processing.pixel_ops.unify import unify_pair
            from shared.image_processing.store_lease import StoreLease

            lease1 = StoreLease.capture(store1)
            lease2 = StoreLease.capture(store2)
            should_abort = signal.should_abort if signal is not None else None
            u1, u2 = unify_pair(
                store1, store2, method, lease1=lease1, lease2=lease2, should_abort=should_abort
            )
            if u1 is not None and u2 is not None:
                self.cache.put_unified(uid1, uid2, method, w, h, (u1, u2))
            return u1, u2
        except Exception as e:
            logger.error(f"Pipeline ensure_unified failed: {e}", exc_info=True)
            return None, None

    # -- lifecycle --

    def cancel(self, key: tuple | None = None) -> None:
        if key is None:
            for sig in list(self._inflight.values()):
                sig.abort()
            self._inflight.clear()
        else:
            sig = self._inflight.pop(key, None)
            if sig is not None:
                sig.abort()

    def clear(self) -> None:
        self.cancel()
        self.cache.clear()
