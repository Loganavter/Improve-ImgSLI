from __future__ import annotations

import logging
import time
from typing import Any

from sli_ui_toolkit.workers import GenericWorker

from shared.rendering.image_identity import image_uid
from tabs.image_compare.services.analysis.runtime import AnalysisRuntime

logger = logging.getLogger("ImproveImgSLI")

class CachedDiffService:
    def __init__(self, store: Any, runtime: AnalysisRuntime):
        self.store = store
        self.runtime = runtime
        self._pending_request_key = None

    def invalidate(self) -> None:
        self.store.viewport.session_data.render_cache.cached_diff_image = None
        self._pending_request_key = None

    def request_generation(self, *, optimize_ssim: bool = False) -> None:
        if not self.runtime.thread_pool:
            return

        document = self.store.get_session_state_slot("document")
        image1 = document.full_res_image1 or document.original_image1
        image2 = document.full_res_image2 or document.original_image2
        diff_mode = self.store.viewport.view_state.diff_mode
        channel_mode = getattr(self.store.viewport.view_state, "channel_view_mode", "RGB")

        if diff_mode != "ssim":
            self.invalidate()
            return
        if not image1 or image2 is None:
            return

        # Identity must be tagged on the original (possibly lazy) object,
        # before any conversion below -- .to_pil() returns a fresh PIL
        # Image each call with an empty .info dict, so tagging after
        # conversion would mint a new uid on every request and defeat
        # request_key-based dedup.
        request_key = (
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
        )
        worker.signals.result.connect(
            lambda diff_image, key=request_key: self._on_diff_map_ready(diff_image, key)
        )
        worker.signals.finished.connect(
            lambda key=request_key: self._on_diff_map_finished(key)
        )
        self.runtime.thread_pool.start(worker, priority=1)

    @staticmethod
    def _generate_diff_map_task(img1, img2, mode, channel_mode, optimize_ssim):
        started_at = time.perf_counter()
        try:
            from shared.image_processing.lazy_pixel_source import LazyPixelSource
            from tabs.image_compare.services.analysis.background_layers import (
                build_cached_diff_image,
            )

            # docs/dev/rendering/tile-rendering-system.md Phase 3: diff needs both
            # full images as real arrays for SSIM; materialize lazy sources
            # here, inside the worker thread (transient, freed after the
            # diff worker finishes) rather than teaching the SSIM path
            # itself about memmap sources.
            if isinstance(img1, LazyPixelSource):
                img1 = img1.to_pil()
            if isinstance(img2, LazyPixelSource):
                img2 = img2.to_pil()

            result = build_cached_diff_image(
                img1,
                img2,
                mode,
                channel_mode,
                optimize_ssim=optimize_ssim,
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
            self.store.viewport.session_data.render_cache.cached_diff_image = diff_image
            self.runtime.core_updates.emit()

    def _on_diff_map_finished(self, request_key) -> None:
        if self._pending_request_key == request_key:
            self._pending_request_key = None
