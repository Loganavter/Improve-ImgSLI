"""SnapshotFrameRenderer — thin orchestrator over prepare/render modules."""

from __future__ import annotations

from PIL import Image

from core.tracing import Tracer
from tabs.image_compare.plugins.video_editor.services.video_export_models import (
    RenderedFrame,
    VideoRenderRequest,
)
from tabs.image_compare.services.video_snapshot_rendering.caches import FrameRenderCaches
from tabs.image_compare.services.video_snapshot_rendering.geometry import (
    fit_source_to_content,
    resolve_prescale_target,
    scale_global_bounds,
)
from tabs.image_compare.services.video_snapshot_rendering.models import PreparedCanvasFrame
from tabs.image_compare.services.video_snapshot_rendering.prepare import (
    prepare_canvas_frame as _prepare_canvas_frame,
    prepare_canvas_frame_from_images as _prepare_canvas_frame_from_images,
)
from tabs.image_compare.services.video_snapshot_rendering.render import render_prepared


class SnapshotFrameRenderer:
    def __init__(self, image_loader, gpu_export_service=None) -> None:
        self._image_loader = image_loader
        self._gpu_export_service = gpu_export_service
        self._last_backend = "gpu"
        self._last_debug: dict = {}
        self._caches = FrameRenderCaches()

    @property
    def last_backend(self) -> str:
        return self._last_backend

    def reset_backend_state(self) -> None:
        self._last_backend = "gpu"
        self._caches.clear()

    def drain_last_debug(self) -> dict:
        data = self._last_debug
        self._last_debug = {}
        return data

    @staticmethod
    def _trace(kind: str, summary: str, payload: dict) -> None:
        if Tracer.enabled():
            Tracer.instance().record(kind, summary, payload)

    # --- static helpers kept for tests / plugin stub subclassing ---

    _resolve_prescale_target = staticmethod(resolve_prescale_target)
    _fit_source_to_content = staticmethod(fit_source_to_content)
    _scale_global_bounds = staticmethod(scale_global_bounds)

    def render(self, snap, request: VideoRenderRequest) -> RenderedFrame:
        if self._gpu_export_service is None:
            raise RuntimeError("GPU export service is not configured")

        result = self._render_gpu(snap, request)
        self._last_backend = result.backend
        self._last_debug = result.debug
        return result

    def prepare_canvas_frame(self, snap, request: VideoRenderRequest) -> PreparedCanvasFrame:
        return _prepare_canvas_frame(
            self._image_loader,
            self._caches,
            snap,
            request,
            trace=self._trace,
        )

    def prepare_canvas_frame_from_images(
        self,
        snap,
        request: VideoRenderRequest,
        image1: Image.Image,
        image2: Image.Image,
        *,
        allow_feature_layout_fallback: bool = False,
        normalize_snapshot: bool = True,
    ) -> PreparedCanvasFrame:
        return _prepare_canvas_frame_from_images(
            self._image_loader,
            self._caches,
            snap,
            request,
            image1,
            image2,
            allow_feature_layout_fallback=allow_feature_layout_fallback,
            normalize_snapshot=normalize_snapshot,
            trace=self._trace,
        )

    def render_from_images(
        self,
        snap,
        request: VideoRenderRequest,
        image1: Image.Image,
        image2: Image.Image,
        *,
        allow_feature_layout_fallback: bool = False,
        normalize_snapshot: bool = True,
    ) -> RenderedFrame:
        prepared = self.prepare_canvas_frame_from_images(
            snap,
            request,
            image1,
            image2,
            allow_feature_layout_fallback=allow_feature_layout_fallback,
            normalize_snapshot=normalize_snapshot,
        )
        result = self._render_prepared(prepared, request)
        self._last_backend = result.backend
        self._last_debug = result.debug
        return result

    def _render_prepared(
        self, prepared: PreparedCanvasFrame, request: VideoRenderRequest
    ) -> RenderedFrame:
        return render_prepared(self._gpu_export_service, prepared, request)

    def _render_gpu(self, snap, request: VideoRenderRequest) -> RenderedFrame:
        prepared = self.prepare_canvas_frame(snap, request)
        return self._render_prepared(prepared, request)
