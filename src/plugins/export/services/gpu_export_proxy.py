import logging
import time
from PySide6.QtCore import QObject, Qt, Signal, Slot
from PySide6.QtWidgets import QApplication
from PIL import Image

from shared.image_processing.regions import build_uniform_tile_grid
from shared.rendering.tab_canvas_services import create_canvas_widget

logger = logging.getLogger("ImproveImgSLI")

# Fixed tile extent for tiled export, capped further by the backend's actual
# max texture size at render time. A fixed constant keeps tile counts
# deterministic across machines/backends for testing; see
# docs/dev/TILED_RENDERING_DESIGN.md "Open questions".
_EXPORT_TILE_MAX_EXTENT = 4096


def _iter_export_tile_rects(canvas_width: int, canvas_height: int, max_extent: int):
    """Yield (left, top, width, height) tile rects covering the export canvas.

    Unlike UniformTileGrid.iter_regions (which clamps to the padded grid
    size), this clamps to the true canvas size so the last row/column never
    reads past the actual export dimensions.
    """
    grid = build_uniform_tile_grid(
        canvas_width, canvas_height, max_tile_width=max_extent
    )
    for row in range(grid.rows):
        top = row * grid.tile_height
        if top >= canvas_height:
            continue
        height = min(grid.tile_height, canvas_height - top)
        for col in range(grid.columns):
            left = col * grid.tile_width
            if left >= canvas_width:
                continue
            width = min(grid.tile_width, canvas_width - left)
            yield left, top, width, height

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

        widget = create_canvas_widget()
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
        from ui.widgets.canvas.rhi_backend import query_max_texture_size

        canvas_w, canvas_h = int(plan.canvas_w), int(plan.canvas_h)
        tile_extent = min(
            _EXPORT_TILE_MAX_EXTENT, query_max_texture_size(widget.rhi())
        )
        if canvas_w <= tile_extent and canvas_h <= tile_extent:
            widget.runtime_state._export_canvas_viewport = None
            return self._render_plan_frame_single(
                widget, plan, diff_image, debug_timings, store=store
            )
        return self._render_plan_frame_tiled(
            widget, plan, diff_image, debug_timings, tile_extent, store=store
        )

    def _render_plan_frame_tiled(
        self, widget, plan, diff_image, debug_timings, tile_extent, store=None
    ):
        from ui.canvas_presentation.plan_applicator import apply_render_plan_to_canvas
        from PySide6.QtGui import QImage as _QImage

        canvas_w, canvas_h = int(plan.canvas_w), int(plan.canvas_h)
        tile_started = time.perf_counter()
        tile_rects = list(
            _iter_export_tile_rects(canvas_w, canvas_h, tile_extent)
        )
        debug_timings["export_tile_count"] = float(len(tile_rects))

        final_image = Image.new("RGBA", (canvas_w, canvas_h))
        for tile_left, tile_top, tile_w, tile_h in tile_rects:
            target_widget_size = (tile_w, tile_h)
            if self._last_widget_size != target_widget_size:
                widget.resize(*target_widget_size)
                widget.show()
                QApplication.processEvents()
                self._last_widget_size = target_widget_size

            widget.runtime_state._export_canvas_viewport = (
                canvas_w,
                canvas_h,
                tile_left,
                tile_top,
            )
            apply_render_plan_to_canvas(widget, plan)
            widget.upload_diff_source_pil_image(diff_image)

            self._render_widget_frame(widget)
            self._render_widget_frame(widget)

            qimg = widget.grabFramebuffer()
            qimg_rgba = qimg.convertToFormat(_QImage.Format.Format_RGBA8888)
            raw_bytes = bytes(qimg_rgba.constBits())
            tile_image = Image.frombytes(
                "RGBA", (qimg_rgba.width(), qimg_rgba.height()), raw_bytes
            )
            if tile_image.size != target_widget_size:
                tile_image = tile_image.resize(
                    target_widget_size, Image.Resampling.BILINEAR
                )
            final_image.paste(tile_image, (tile_left, tile_top))

        widget.runtime_state._export_canvas_viewport = None
        debug_timings["export_tiled_total_ms"] = (
            time.perf_counter() - tile_started
        ) * 1000.0
        debug_timings["readback_width"] = float(canvas_w)
        debug_timings["readback_height"] = float(canvas_h)
        return final_image

    def _render_plan_frame_single(
        self, widget, plan, diff_image, debug_timings, store=None
    ):
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
