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
        if not payload["event"].wait(timeout=2.0):
            raise TimeoutError("GPU marshal timed out waiting for GUI thread")
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

    def render_plan_async(
        self,
        plan,
        *,
        store=None,
        diff_image=None,
        callback,
    ) -> None:
        """Non-blocking counterpart to :meth:`render_plan`.

        Submits the render request and returns immediately — the caller's
        thread is never parked on an ``Event.wait()``. ``callback(image,
        debug_timings, error)`` is invoked later, on the main thread, once
        the render actually runs there. Intended for callers that must keep
        their (background) thread free for other work while the GPU request
        is in flight — e.g. thumbnail generation — not for one-shot,
        user-initiated exports, which should keep using ``render_plan``.
        """
        app = QApplication.instance()
        if app is None:
            raise RuntimeError("QApplication is not available for GPU export")

        self._proxy.render_requested.emit(
            {
                "mode": "render_plan",
                "plan": plan,
                "store": store,
                "diff_image": diff_image,
                "callback": callback,
            }
        )

    def warm_up(self) -> None:
        """Create the offscreen render widget ahead of the first real request.

        The widget (and its QRhi context/surface) is normally created lazily
        on first use, which pays window/GPU-context creation cost inline with
        that first render — visible as a multi-second stall the first time a
        dialog needs it. Call this once, early and off the interactive path,
        so the cost is paid before the user notices.

        Best-effort: this fires on a startup timer and again whenever the
        host re-triggers it once a canvas-providing tab becomes active,
        since not every tab can answer the canvas-widget-class lookup (see
        `tab_canvas_services.get_canvas_widget_class`) — a call landing
        while some other tab is active is an expected, common miss, not a
        real error, so it's logged as a short message rather than a full
        traceback. Either way, a failure here just means we fall back to the
        original lazy creation on first real use — it must never surface as
        an unhandled exception.
        """
        app = QApplication.instance()
        if app is None:
            return
        try:
            self._proxy._ensure_widget()
        except Exception as e:
            logger.debug("GPU export widget warm-up skipped (not ready yet): %s", e)

    def shutdown(self) -> None:
        app = QApplication.instance()
        if app is None:
            return
        try:
            self._proxy.shutdown()
            app.processEvents()
        except Exception:
            logger.exception("GPU export shutdown failed")