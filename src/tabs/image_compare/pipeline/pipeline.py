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

    def __init__(self, cache: PipelineCache | None = None, store=None):
        self.cache = cache or PipelineCache()
        # in-flight key -> AbortSignal (single-flight dedup)
        self._inflight: dict[tuple, AbortSignal] = {}
        self._store = store

    def set_store(self, store) -> None:
        self._store = store

    def _pipeline_state(self):
        if self._store is None:
            return None
        try:
            return self._store.get_session_state_slot("pipeline")
        except Exception:
            return None

    def _peek_from_state(self, kind: str, path: str, crop_service=None, auto_crop: bool | None = None):
        st = self._pipeline_state()
        if st is None:
            return None
        try:
            if kind == "pixel":
                from tabs.image_compare.pipeline.cache import _pixel_key
                key = _pixel_key(path, crop_service, auto_crop)
                val = st.pixel.get(key) if hasattr(st, "pixel") else None
            elif kind == "preview":
                from tabs.image_compare.pipeline.cache import _preview_key
                key = _preview_key(path, crop_service, auto_crop)
                val = st.preview.get(key) if hasattr(st, "preview") else None
            else:
                return None
        except Exception:
            return None
        if val is None:
            return None
        try:
            if hasattr(val, "isNull") and val.isNull():
                return None
        except Exception:
            pass
        try:
            is_open = getattr(val, "is_open", None)
            if is_open is not None:
                if callable(is_open):
                    if not is_open():
                        return None
                elif not is_open:
                    return None
        except Exception:
            pass
        return val

    # -- sync peek (no decode) --

    def peek(self, path: str, crop_service=None, auto_crop: bool | None = None):
        if isinstance(crop_service, bool) and auto_crop is None:
            auto_crop = crop_service
            crop_service = None
        eff = crop_service if crop_service is not None else getattr(self.cache, "crop_service", None)
        hit = self._peek_from_state("pixel", path, eff if auto_crop is None else eff, auto_crop)
        if hit is not None:
            return hit
        if auto_crop is not None:
            return self.cache.get_pixel(path, eff, auto_crop)
        return self.cache.get_pixel(path, eff)

    def peek_preview(self, path: str, crop_service=None, auto_crop: bool | None = None):
        if isinstance(crop_service, bool) and auto_crop is None:
            auto_crop = crop_service
            crop_service = None
        eff = crop_service if crop_service is not None else getattr(self.cache, "crop_service", None)
        hit = self._peek_from_state("preview", path, eff if auto_crop is None else eff, auto_crop)
        if hit is not None:
            return hit
        if auto_crop is not None:
            return self.cache.get_preview(path, eff, auto_crop)
        return self.cache.get_preview(path, eff)

    # -- ensure tiers --

    def ensure_pixel(
        self, path: str, crop_service=None, auto_crop: bool | None = None, signal: AbortSignal | None = None
    ):
        if isinstance(crop_service, bool) and auto_crop is None:
            auto_crop = crop_service
            crop_service = None
        # сигнал может быть передан позиционно как третий arg в старых вызовах ensure_pixel(path, True, signal)
        if isinstance(signal, bool):
            auto_crop = signal  # type: ignore
            signal = None
        if signal is not None and getattr(signal, "is_aborted", lambda: False)():
            return None
        eff = crop_service if crop_service is not None else getattr(self.cache, "crop_service", None)
        cached = self.cache.get_pixel(path, eff, auto_crop) if auto_crop is not None else self.cache.get_pixel(path, eff)
        if cached is not None:
            return cached
        try:
            if auto_crop is not None:
                store = self.cache.get_or_load(path, eff, auto_crop)
            else:
                store = self.cache.get_or_load(path, eff)
            return store
        except Exception as e:
            logger.error(f"Pipeline ensure_pixel failed for {path}: {e}", exc_info=True)
            return None

    def ensure_preview(
        self, path: str, crop_service=None, auto_crop: bool | None = None, signal: AbortSignal | None = None
    ):
        if isinstance(crop_service, bool) and auto_crop is None:
            auto_crop = crop_service
            crop_service = None
        if isinstance(signal, bool):
            auto_crop = signal  # type: ignore
            signal = None
        if signal is not None and getattr(signal, "is_aborted", lambda: False)():
            return None
        eff = crop_service if crop_service is not None else getattr(self.cache, "crop_service", None)
        if auto_crop is not None:
            cached = self.cache.get_preview(path, eff, auto_crop)
        else:
            cached = self.cache.get_preview(path, eff)
        if cached is not None:
            return cached
        try:
            if auto_crop is not None:
                return self.cache.get_or_load_preview(path, eff, auto_crop)
            return self.cache.get_or_load_preview(path, eff)
        except Exception as e:
            logger.error(f"Pipeline ensure_preview failed for {path}: {e}", exc_info=True)
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
        # use image_uid (counter/cacheKey fallback) for GC-safe identity, not id()
        from shared.rendering.image_identity import image_uid

        uid1 = image_uid(store1)
        uid2 = image_uid(store2)
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

            should_abort = signal.should_abort if signal is not None else None
            u1, u2 = unify_pair(
                store1, store2, method, should_abort=should_abort
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
