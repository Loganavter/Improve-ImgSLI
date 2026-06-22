import logging
import time
from PySide6.QtCore import QObject, Qt, Signal, Slot
from PySide6.QtWidgets import QApplication
from PIL import Image

from ui.widgets.gl_canvas import GLCanvas

from .gpu_export_scene import qimage_to_pil

logger = logging.getLogger("ImproveImgSLI")

class GpuExportProxy(QObject):
    render_requested = Signal(object)

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

    @Slot()
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

    def _render_widget_frame(self, widget):
        # QRhiWidget renders in its own render(cb) callback. Requesting an
        # update + flushing the event loop schedules a frame; grabFramebuffer()
        # then performs a synchronous render and returns the QImage.
        widget.update()
        QApplication.processEvents()

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
            self._render_widget_frame(widget)
            QApplication.processEvents()

        paint_started = time.perf_counter()
        self._render_widget_frame(widget)
        debug_timings["paint_gl_ms"] = (
            time.perf_counter() - paint_started
        ) * 1000.0

        framebuffer_started = time.perf_counter()
        grab_started = time.perf_counter()
        qimg = widget.grabFramebuffer()
        debug_timings["grab_raw_ms"] = (time.perf_counter() - grab_started) * 1000.0

        convert_started = time.perf_counter()
        from PySide6.QtGui import QImage as _QImage
        qimg_rgba = qimg.convertToFormat(_QImage.Format.Format_RGBA8888)
        debug_timings["qimage_convert_ms"] = (time.perf_counter() - convert_started) * 1000.0

        bits_started = time.perf_counter()
        ptr = qimg_rgba.constBits()
        raw_bytes = bytes(ptr)
        debug_timings["qimage_bits_ms"] = (time.perf_counter() - bits_started) * 1000.0

        pil_started = time.perf_counter()
        image = Image.frombytes(
            "RGBA",
            (qimg_rgba.width(), qimg_rgba.height()),
            raw_bytes,
        )
        debug_timings["pil_frombytes_ms"] = (time.perf_counter() - pil_started) * 1000.0
        # Cache the raw RGBA bytes alongside the PIL image so downstream consumers
        # (notably the video export ffmpeg-write loop) can skip a redundant
        # PIL.tobytes() memcpy when no resize/composite is needed. ~5ms saved
        # per 4K frame in measurements.
        image._raw_rgba_bytes = raw_bytes

        resize_started = time.perf_counter()
        if image.size != target_widget_size:
            image = image.resize(target_widget_size, Image.Resampling.BILINEAR)
            # Resize allocates new buffers; the cached raw bytes no longer match.
            if hasattr(image, "_raw_rgba_bytes"):
                try:
                    delattr(image, "_raw_rgba_bytes")
                except AttributeError:
                    pass
        debug_timings["pil_resize_ms"] = (time.perf_counter() - resize_started) * 1000.0

        debug_timings["grab_framebuffer_ms"] = (
            time.perf_counter() - framebuffer_started
        ) * 1000.0
        debug_timings["readback_width"] = float(image.width)
        debug_timings["readback_height"] = float(image.height)
        return image

    @Slot(object)
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
