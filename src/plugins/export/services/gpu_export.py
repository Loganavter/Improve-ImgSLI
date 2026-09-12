import logging

from PIL import Image
from PySide6.QtWidgets import QApplication

from .gpu_export_proxy import GpuExportProxy

logger = logging.getLogger("ImproveImgSLI")

class GpuExportService:
    def __init__(self, parent=None, resource_manager=None):
        self._proxy = GpuExportProxy(parent, resource_manager=resource_manager)

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

    def render_plan(
        self,
        plan,
        *,
        store=None,
        diff_image=None,
    ) -> Image.Image:
        app = QApplication.instance()
        if app is None:
            raise RuntimeError("QApplication is not available for GPU export")

        result = self._request(
            {
                "mode": "render_plan",
                "plan": plan,
                "store": store,
                "diff_image": diff_image,
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
