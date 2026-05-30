import logging
import time
from PyQt6.QtCore import QObject, Qt, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import QApplication
from OpenGL import GL as gl
from PIL import Image

from ui.widgets.gl_canvas import GLCanvas
from ui.widgets.gl_canvas.render import paint_gl

logger = logging.getLogger("ImproveImgSLI")

class GpuExportProxy(QObject):
    render_requested = pyqtSignal(object)

    def __init__(self, parent=None, resource_manager=None):
        super().__init__(parent)
        self._widget = None
        self._resource_manager = resource_manager
        self._last_widget_size = None
        self.render_requested.connect(self._render_on_main_thread)

    def _ensure_widget(self):
        if self._widget is not None:
            return self._widget

        widget = GLCanvas()
        widget.setObjectName("gpu_export_canvas")
        widget.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        widget.setAutoFillBackground(False)
        widget._use_plan_fill_clear = True
        widget.show()
        QApplication.processEvents()
        if self._resource_manager is not None:
            self._resource_manager.register_widget(widget, name="gpu_export_canvas")
        self._widget = widget
        return widget

    @pyqtSlot()
    def shutdown(self):
        widget = self._widget
        self._widget = None
        self._last_widget_size = None
        if widget is None:
            return
        try:
            widget.hide()
        except Exception:
            pass
        try:
            widget.close()
        except Exception:
            pass
        try:
            widget.deleteLater()
        except Exception:
            pass

    def _render_widget_frame(self, widget, target_size: tuple[int, int] | None = None):
        old_forced_dpr = getattr(widget, "_forced_device_pixel_ratio", None)
        widget._forced_device_pixel_ratio = 1.0
        try:
            if hasattr(widget, "makeCurrent"):
                widget.makeCurrent()
                try:
                    if target_size is not None:
                        gl.glViewport(
                            0,
                            0,
                            max(1, int(target_size[0])),
                            max(1, int(target_size[1])),
                        )
                    paint_gl(widget)
                finally:
                    widget.doneCurrent()
            else:
                widget.update()
            QApplication.processEvents()
        finally:
            if old_forced_dpr is None:
                try:
                    delattr(widget, "_forced_device_pixel_ratio")
                except AttributeError:
                    pass
            else:
                widget._forced_device_pixel_ratio = old_forced_dpr

    @staticmethod
    def _read_widget_framebuffer_to_pil(width: int, height: int) -> Image.Image:
        width = max(1, int(width))
        height = max(1, int(height))
        gl.glPixelStorei(gl.GL_PACK_ALIGNMENT, 1)
        gl.glFinish()
        raw = gl.glReadPixels(0, 0, width, height, gl.GL_RGBA, gl.GL_UNSIGNED_BYTE)
        if hasattr(raw, "tobytes"):
            raw = raw.tobytes()
        return Image.frombytes("RGBA", (width, height), bytes(raw)).transpose(
            Image.Transpose.FLIP_TOP_BOTTOM
        )

    def _grab_rendered_frame(self, widget, target_size: tuple[int, int]) -> Image.Image:
        if not hasattr(widget, "makeCurrent"):
            return Image.new("RGBA", target_size, (0, 0, 0, 0))
        widget.makeCurrent()
        try:
            return self._read_widget_framebuffer_to_pil(*target_size)
        finally:
            widget.doneCurrent()

    def _render_plan_frame(self, widget, plan, diff_image, debug_timings, store=None):
        from ui.canvas_presentation.plan_applicator import apply_render_plan_to_canvas

        resize_show_started = time.perf_counter()
        target_widget_size = (int(plan.canvas_w), int(plan.canvas_h))
        widget_size_changed = self._last_widget_size != target_widget_size
        if widget_size_changed:
            widget.resize(*target_widget_size)
            widget.show()
            QApplication.processEvents()
            self._last_widget_size = target_widget_size
        debug_timings["widget_resize_show_ms"] = (
            time.perf_counter() - resize_show_started
        ) * 1000.0

        configure_started = time.perf_counter()
        apply_render_plan_to_canvas(widget, plan)
        widget.upload_diff_source_pil_image(diff_image)
        debug_timings["configure_widget_ms"] = (
            time.perf_counter() - configure_started
        ) * 1000.0

        if widget_size_changed:
            self._render_widget_frame(widget, target_widget_size)
            QApplication.processEvents()

        paint_started = time.perf_counter()
        self._render_widget_frame(widget, target_widget_size)
        debug_timings["paint_gl_ms"] = (
            time.perf_counter() - paint_started
        ) * 1000.0

        framebuffer_started = time.perf_counter()
        image = self._grab_rendered_frame(widget, target_widget_size)
        debug_timings["grab_framebuffer_ms"] = (
            time.perf_counter() - framebuffer_started
        ) * 1000.0
        debug_timings["readback_width"] = float(image.width)
        debug_timings["readback_height"] = float(image.height)
        return image

    @pyqtSlot(object)
    def _render_on_main_thread(self, payload):
        event = payload["event"]
        result_box = payload["result_box"]
        debug_timings = {}
        try:
            widget = self._ensure_widget()
            mode = payload.get("mode", "render")
            if mode != "render_plan":
                raise RuntimeError(f"Unsupported GPU export mode: {mode}")
            plan = payload["plan"]
            store = payload.get("store")
            diff_image = payload.get("diff_image")
            result_box["image"] = self._render_plan_frame(
                widget,
                plan,
                diff_image,
                debug_timings,
                store=store,
            )
            result_box["debug_timings"] = debug_timings
        except Exception as exc:
            logger.exception("GPU export rendering failed")
            result_box["error"] = exc
        finally:
            event.set()
