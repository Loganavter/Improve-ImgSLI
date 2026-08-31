from __future__ import annotations

import logging
import time
from typing import Any

from sli_ui_toolkit.workers import GenericWorker

from core.state_management.actions import SetCachedDiffImageAction

from shared.image_processing.store_lease import StoreLease
from shared.rendering.image_identity import image_uid
from tabs.image_compare.services.analysis.runtime import AnalysisRuntime

logger = logging.getLogger("ImproveImgSLI")

class CachedDiffService:
    def __init__(self, store: Any, runtime: AnalysisRuntime):
        self.store = store
        self.runtime = runtime
        self._pending_request_key: tuple | None = None

    def invalidate(self) -> None:
        render_cache = self.store.viewport.session_data.render_cache
        dispatcher = getattr(self.store, "get_dispatcher", None)
        dispatcher = dispatcher() if callable(dispatcher) else None
        if dispatcher is not None:
            try:
                dispatcher.dispatch(SetCachedDiffImageAction(image=None), scope="viewport")
            except Exception:
                logger.error("Failed to dispatch SetCachedDiffImageAction", exc_info=True)
                try:
                    setattr(render_cache, "cached_diff_image", None)
                except Exception:
                    pass
        else:
            try:
                setattr(render_cache, "cached_diff_image", None)
            except Exception:
                pass
        # Must be cleared alongside cached_diff_image: a stale
        # cached_diff_source_key surviving a real invalidation (diff mode
        # or channel-view-mode change) would make
        # request_cached_diff_image_async think a same-images-different-mode
        # request was already served and skip recomputing entirely (see
        # that method's cached_diff_source_key comparison).
        # No dedicated action for source_key — update via setattr to avoid dogma.
        # Must target the *current* store viewport after dispatch (which replaced
        # the render_cache instance), not the pre-dispatch `render_cache` variable.
        try:
            setattr(self.store.viewport.session_data.render_cache, "cached_diff_source_key", None)
        except Exception:
            pass
        self._pending_request_key = None

    def _peek_slot(self, slot: int):
        doc = self.store.get_session_state_slot("document")
        path = doc.image1_path if slot == 1 else doc.image2_path
        if not path:
            return None
        try:
            vp = self.store.viewport.session_data.image_state
            cand = vp.image1 if slot == 1 else vp.image2
            if cand is not None:
                try:
                    if hasattr(cand, "isNull") and cand.isNull():
                        cand = None
                    elif hasattr(cand, "is_open") and not cand.is_open:
                        cand = None
                except Exception:
                    pass
                if cand is not None:
                    return cand
        except Exception:
            pass
        try:
            ps = self.store.get_session_state_slot("pipeline")
            if ps is not None:
                import os

                from tabs.image_compare.pipeline.cache import _pixel_key, _preview_key

                for cache_dict, key_fn in ((ps.pixel, _pixel_key), (ps.preview, _preview_key)):
                    try:
                        k = key_fn(path, None, None)
                        v = cache_dict.get(k)
                        if v is not None:
                            if hasattr(v, "is_open") and not v.is_open:
                                continue
                            if hasattr(v, "isNull") and v.isNull():
                                continue
                            return v
                    except Exception:
                        pass
                    try:
                        norm = os.path.normpath(path)
                        for kk, vv in cache_dict.items():
                            if kk[0] == norm:
                                if hasattr(vv, "is_open") and not vv.is_open:
                                    continue
                                if hasattr(vv, "isNull") and vv.isNull():
                                    continue
                                return vv
                    except Exception:
                        pass
        except Exception:
            pass
        return None

    def request_generation(self, *, optimize_ssim: bool = False) -> None:
        if not self.runtime.thread_pool:
            return

        image1 = self._peek_slot(1)
        image2 = self._peek_slot(2)
        diff_mode = self.store.viewport.view_state.diff_mode
        channel_mode = getattr(self.store.viewport.view_state, "channel_view_mode", "RGB")

        if diff_mode != "ssim":
            self.invalidate()
            return
        if not image1 or image2 is None:
            return

        # Identity must be tagged on the original (possibly lazy) object,
        # before any conversion below -- materializing a TiledPixelStore
        # returns a fresh PIL Image each call with an empty .info dict, so
        # tagging after conversion would mint a new uid on every request and
        # defeat request_key-based dedup.
        request_key: tuple = (
            diff_mode,
            channel_mode,
            image_uid(image1),
            image_uid(image2),
            getattr(image1, "size", None),
            getattr(image2, "size", None),
        )
        self._pending_request_key = request_key

        worker = GenericWorker(
            self._generate_diff_map_task,
            image1,
            image2,
            diff_mode,
            channel_mode,
            optimize_ssim,
            StoreLease.capture(image1),
            StoreLease.capture(image2),
        )
        worker.signals.result.connect(
            lambda diff_image, key=request_key: self._on_diff_map_ready(diff_image, key)
        )
        worker.signals.finished.connect(
            lambda key=request_key: self._on_diff_map_finished(key)
        )
        self.runtime.thread_pool.start(worker, priority=1)

    @staticmethod
    def _generate_diff_map_task(
        img1, img2, mode, channel_mode, optimize_ssim, lease1, lease2
    ):
        started_at = time.perf_counter()
        try:
            from tabs.image_compare.services.analysis.background_layers import (
                build_cached_diff_image,
            )

            result = build_cached_diff_image(
                img1,
                img2,
                mode,
                channel_mode,
                optimize_ssim=optimize_ssim,
                lease1=lease1,
                lease2=lease2,
            )
            logger.debug(
                "[DIFF_TASK] mode=%s channel=%s size1=%s size2=%s elapsed_ms=%.1f result=%s",
                mode,
                channel_mode,
                getattr(img1, "size", None),
                getattr(img2, "size", None),
                (time.perf_counter() - started_at) * 1000.0,
                getattr(result, "size", None),
            )
            return result
        except Exception:
            logger.exception("Failed to build cached diff image")
            return None

    def _on_diff_map_ready(self, diff_image, request_key) -> None:
        if self._pending_request_key != request_key:
            return
        if diff_image is not None:
            dispatcher = getattr(self.store, "get_dispatcher", None)
            dispatcher = dispatcher() if callable(dispatcher) else None
            if dispatcher is not None:
                try:
                    dispatcher.dispatch(SetCachedDiffImageAction(image=diff_image), scope="viewport")
                except Exception:
                    logger.error("Failed to dispatch SetCachedDiffImageAction", exc_info=True)
                    try:
                        setattr(self.store.viewport.session_data.render_cache, "cached_diff_image", diff_image)
                    except Exception:
                        pass
            else:
                try:
                    setattr(self.store.viewport.session_data.render_cache, "cached_diff_image", diff_image)
                except Exception:
                    pass
            self.runtime.core_updates.emit()

    def _on_diff_map_finished(self, request_key) -> None:
        if self._pending_request_key == request_key:
            self._pending_request_key = None
