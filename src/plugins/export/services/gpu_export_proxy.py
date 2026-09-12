import logging
import time
from PySide6.QtCore import QObject, Qt, Signal, Slot
from PySide6.QtWidgets import QApplication
from PIL import Image

from shared.rendering.export_tiling import (
    DEFAULT_EXPORT_TILE_MAX_EXTENT,
    TiledFramebufferExporter,
    iter_export_tile_rects,
    qimage_to_pil_rgba,
)
from shared.rendering.offscreen_canvas import (
    configure_offscreen_widget,
    render_widget_frame,
    resize_offscreen_widget,
    show_offscreen_widget,
    shutdown_offscreen_widget,
)
from shared.rendering.tab_canvas_services import create_canvas_widget

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

        widget = create_canvas_widget()
        widget.setObjectName("gpu_export_canvas")
        configure_offscreen_widget(widget)
        widget._use_plan_fill_clear = True
        show_offscreen_widget(widget)
        if self._resource_manager is not None:
            self._resource_manager.register_widget(widget, name="gpu_export_canvas")
        self._widget = widget
        return widget

    @Slot()
    def shutdown(self):
        widget = self._widget
        self._widget = None
        self._last_widget_size = None
        shutdown_offscreen_widget(widget)

    def _render_widget_frame(self, widget):
        render_widget_frame(widget)

    def _build_exporter(self, widget, plan, diff_image):
        from ui.canvas_presentation.plan_applicator import apply_render_plan_to_canvas
        from ui.widgets.canvas.rhi_backend import query_max_texture_size

        def set_export_viewport(viewport):
            widget.runtime_state._export_canvas_viewport = viewport

        def prepare_frame():
            apply_render_plan_to_canvas(widget, plan)
            widget.upload_diff_source_pil_image(diff_image)

        return TiledFramebufferExporter(
            widget,
            set_export_viewport=set_export_viewport,
            prepare_frame=prepare_frame,
            query_max_texture_size=lambda: query_max_texture_size(widget.rhi()),
        )

    def _render_plan_frame(self, widget, plan, diff_image, debug_timings, store=None):
        from ui.widgets.canvas.rhi_backend import query_max_texture_size

        canvas_w, canvas_h = int(plan.canvas_w), int(plan.canvas_h)
        tile_extent = min(
            DEFAULT_EXPORT_TILE_MAX_EXTENT, query_max_texture_size(widget.rhi())
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
        canvas_w, canvas_h = int(plan.canvas_w), int(plan.canvas_h)
        tile_started = time.perf_counter()
        tile_rects = list(iter_export_tile_rects(canvas_w, canvas_h, tile_extent))
        debug_timings["export_tile_count"] = float(len(tile_rects))

        exporter = self._build_exporter(widget, plan, diff_image)
        final_image = exporter.render_rgba(
            canvas_w, canvas_h, max_extent=tile_extent
        )
        self._last_widget_size = exporter._last_size

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
            resize_offscreen_widget(widget, target_widget_size)
            show_offscreen_widget(widget)
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
        image = qimage_to_pil_rgba(qimg)
        debug_timings["qimage_convert_ms"] = (time.perf_counter() - convert_started) * 1000.0

        raw_bytes = image.tobytes()
        image._raw_rgba_bytes = raw_bytes

        resize_started = time.perf_counter()
        if image.size != target_widget_size:
            image = image.resize(target_widget_size, Image.Resampling.BILINEAR)
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
