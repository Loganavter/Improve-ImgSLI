import logging

from PIL import Image
from PyQt6.QtWidgets import QApplication

from plugins.export.models import ExportRenderContext

from .gpu_export_layout import compute_canvas_plan as _compute_canvas_plan
from .gpu_export_proxy import GpuExportProxy

logger = logging.getLogger("ImproveImgSLI")

class GpuExportService:
    def __init__(self, parent=None, resource_manager=None):
        self._proxy = GpuExportProxy(parent, resource_manager=resource_manager)
        self._max_texture_size = None
        self._last_tiled_debug = {}

    def _request(self, payload: dict):
        import threading

        payload.setdefault("event", threading.Event())
        payload.setdefault("result_box", {})
        self._proxy.render_requested.emit(payload)
        payload["event"].wait()
        error = payload["result_box"].get("error")
        if error is not None:
            raise error
        return payload["result_box"]

    def _get_max_texture_size(self) -> int:
        if self._max_texture_size is None:
            result = self._request({"mode": "limits"})
            self._max_texture_size = int(result.get("max_texture_size", 0) or 0)
        return max(1, self._max_texture_size)

    def render_image(
        self,
        store,
        image1=None,
        image2=None,
        width: int | None = None,
        height: int | None = None,
        render_context: ExportRenderContext | None = None,
        magnifier_drawing_coords=None,
        prepared_background_layers=None,
        force_tiled: bool = False,
        min_tiles_per_axis: int = 2,
    ) -> Image.Image:
        app = QApplication.instance()
        if app is None:
            raise RuntimeError("QApplication is not available for GPU export")

        if render_context is None:
            if image1 is None or image2 is None or width is None or height is None:
                raise ValueError(
                    "GPU render_image requires either render_context or explicit image arguments"
                )
            render_context = ExportRenderContext(
                image1=image1,
                image2=image2,
                width=width,
                height=height,
                source_image1=image1,
                source_image2=image2,
                source_key=None,
                magnifier_drawing_coords=magnifier_drawing_coords,
                prepared_background_layers=prepared_background_layers,
                cached_diff_image=None,
            )

        mode = "render"
        max_texture_size = self._get_max_texture_size()
        if (
            force_tiled
            or render_context.width > max_texture_size
            or render_context.height > max_texture_size
        ):
            mode = "render_tiled"

        result = self._request(
            {
                "mode": mode,
                "store": store,
                "render_context": render_context,
                "min_tiles_per_axis": max(1, int(min_tiles_per_axis)),
            }
        )
        image = result.get("image")
        if image is None:
            raise RuntimeError("GPU export returned no image")
        return image, dict(result.get("debug_timings") or {})

    def shutdown(self) -> None:
        app = QApplication.instance()
        if app is None:
            return
        try:
            self._proxy.shutdown()
            app.processEvents()
        except Exception:
            logger.exception("GPU export shutdown failed")
