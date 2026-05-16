import logging
import threading
import time
from OpenGL import GL as gl
from PyQt6.QtCore import QObject, Qt, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import QApplication

from domain.types import Rect
from plugins.export.models import ExportRenderContext
from ui.canvas_infra.scene.property_access import (
    read_canvas_feature_color_by_setting_key,
    read_canvas_feature_setting_by_key,
)
from ui.canvas_presentation.plan_builder import (
    build_canvas_plan,
    compute_canvas_plan,
)
from ui.widgets.gl_canvas import GLCanvas
from ui.widgets.gl_canvas.render import paint_gl

from .gpu_export_images import prepare_scene_images
from .gpu_export_layout import compute_export_stroke_scales
from .gpu_export_scene import (
    adjust_scene_for_padded_canvas,
    build_divider_export_overlay,
    build_export_gl_scene,
    qimage_to_pil,
    query_active_magnifier_divider_thickness,
    query_guides_state,
)
from .gpu_export_tiled import render_tiled_image

logger = logging.getLogger("ImproveImgSLI")

class GpuExportProxy(QObject):
    render_requested = pyqtSignal(object)

    def __init__(self, parent=None, resource_manager=None):
        super().__init__(parent)
        self._widget = None
        self._resource_manager = resource_manager
        self._scene_images_cache = {}
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
        self._scene_images_cache.clear()
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

    def _save_viewport_geometry(self, store) -> dict:
        viewport = store.viewport
        return {
            "pixmap_width": getattr(viewport.geometry_state, "pixmap_width", 0),
            "pixmap_height": getattr(viewport.geometry_state, "pixmap_height", 0),
            "image_display_rect_on_label": getattr(
                viewport,
                "image_display_rect_on_label",
                Rect(),
            ),
        }

    def _restore_viewport_geometry(self, store, state: dict) -> None:
        viewport = store.viewport
        viewport.geometry_state.pixmap_width = state["pixmap_width"]
        viewport.geometry_state.pixmap_height = state["pixmap_height"]
        viewport.geometry_state.image_display_rect_on_label = state["image_display_rect_on_label"]

    def _get_max_texture_size(self, widget) -> int:
        if not hasattr(widget, "makeCurrent"):
            return 4096
        widget.makeCurrent()
        try:
            value = int(gl.glGetIntegerv(gl.GL_MAX_TEXTURE_SIZE))
        finally:
            widget.doneCurrent()
        return max(1, value)

    def _render_widget_frame(self, widget):
        if hasattr(widget, "makeCurrent"):
            widget.makeCurrent()
            try:
                paint_gl(widget)
            finally:
                widget.doneCurrent()
        else:
            widget.update()
        QApplication.processEvents()

    def _configure_widget_manual(
        self,
        widget,
        store,
        scene_images: dict,
        canvas_plan: dict,
        render_context: ExportRenderContext,
        stroke_scales: tuple[float, float, float],
    ):
        from ui.canvas_presentation.plan_applicator import apply_render_plan_to_canvas

        vp = store.viewport
        view = vp.view_state
        capture_visible = bool(read_canvas_feature_setting_by_key(vp, "capture.visible"))
        capture_color = read_canvas_feature_color_by_setting_key(vp, "capture.color")
        guides_state = query_guides_state(view)
        scale_x, scale_y, scale_ref = stroke_scales
        image_w = canvas_plan.image_width
        image_h = canvas_plan.image_height
        canvas_w = canvas_plan.canvas_width
        canvas_h = canvas_plan.canvas_height
        pad_left = canvas_plan.padding_left
        pad_top = canvas_plan.padding_top

        divider_overlay = build_divider_export_overlay(
            store,
            scale_x=scale_x,
            scale_y=scale_y,
            content_offset_x=pad_left,
            content_offset_y=pad_top,
            content_width=image_w,
            content_height=image_h,
        )
        divider_thickness_export = int(divider_overlay.get("thickness", 0))
        guides_thickness_export = int(guides_state.thickness)
        magnifier_divider_thickness_export = query_active_magnifier_divider_thickness(store)
        gl_scene = build_export_gl_scene(store, divider_thickness_export)
        gl_scene = adjust_scene_for_padded_canvas(
            gl_scene,
            pad_left=pad_left,
            pad_top=pad_top,
            image_w=image_w,
            image_h=image_h,
            canvas_w=canvas_w,
            canvas_h=canvas_h,
        )

        plan = build_canvas_plan(
            store,
            scene_images["bg1"],
            scene_images["bg2"],
            source_image1=scene_images["src1"],
            source_image2=scene_images["src2"],
            source_key=render_context.source_key,
            target_size=(canvas_w, canvas_h),
            content_size=(image_w, image_h),
            pad_left=pad_left,
            pad_top=pad_top,
            gl_scene=gl_scene,
            divider_thickness_px=magnifier_divider_thickness_export,
            guides_thickness=guides_thickness_export,
            output_scale=1.0,
        )

        apply_render_plan_to_canvas(widget, plan)
        widget.upload_diff_source_pil_image(scene_images["diff"])

    @pyqtSlot(object)
    def _render_on_main_thread(self, payload):
        event = payload["event"]
        result_box = payload["result_box"]
        viewport_state = None
        store = payload.get("store")
        debug_timings = {}
        try:
            widget = self._ensure_widget()
            mode = payload.get("mode", "render")
            if mode == "limits":
                result_box["max_texture_size"] = self._get_max_texture_size(widget)
                return
            store = payload["store"]
            render_context = payload.get("render_context")
            if render_context is None:
                render_context = ExportRenderContext(
                    image1=payload["image1"],
                    image2=payload["image2"],
                    width=int(payload["width"]),
                    height=int(payload["height"]),
                    source_image1=payload.get("source_image1") or payload["image1"],
                    source_image2=payload.get("source_image2") or payload["image2"],
                    source_key=payload.get("source_key"),
                    overlay_drawing_coords=payload.get("overlay_drawing_coords"),
                    prepared_background_layers=payload.get("prepared_background_layers"),
                    cached_diff_image=payload.get("cached_diff_image"),
                )
            width = int(render_context.width)
            height = int(render_context.height)
            viewport_state = self._save_viewport_geometry(store)
            stroke_scales = compute_export_stroke_scales(
                viewport_state,
                width,
                height,
            )
            if mode == "render_tiled":
                min_tiles_per_axis = max(
                    1, int(payload.get("min_tiles_per_axis", 2) or 2)
                )
                tiled_started = time.perf_counter()
                tiled_image, tiled_debug = render_tiled_image(
                    widget=widget,
                    store=store,
                    render_context=render_context,
                    width=width,
                    height=height,
                    prepared_background_layers=render_context.prepared_background_layers,
                    min_tiles_per_axis=min_tiles_per_axis,
                    stroke_scales=stroke_scales,
                    get_max_texture_size=self._get_max_texture_size,
                    render_widget_frame=self._render_widget_frame,
                )
                result_box["image"] = tiled_image
                debug_timings["tiled_total_ms"] = (
                    time.perf_counter() - tiled_started
                ) * 1000.0
                debug_timings["tiled_min_tiles_per_axis"] = float(min_tiles_per_axis)
                debug_timings.update(tiled_debug or {})
                result_box["debug_timings"] = debug_timings
                return

            canvas_started = time.perf_counter()
            canvas_plan = compute_canvas_plan(
                store,
                width,
                height,
                overlay_drawing_coords=render_context.overlay_drawing_coords,
            )
            debug_timings["canvas_plan_ms"] = (
                time.perf_counter() - canvas_started
            ) * 1000.0
            canvas_w = canvas_plan.canvas_width
            canvas_h = canvas_plan.canvas_height

            prepare_started = time.perf_counter()
            scene_images = prepare_scene_images(
                self._scene_images_cache,
                render_context,
                canvas_plan,
            )
            debug_timings["prepare_scene_images_ms"] = (
                time.perf_counter() - prepare_started
            ) * 1000.0

            resize_show_started = time.perf_counter()
            target_widget_size = (canvas_w, canvas_h)
            if self._last_widget_size != target_widget_size:
                widget.resize(canvas_w, canvas_h)
                widget.show()
                QApplication.processEvents()
                self._last_widget_size = target_widget_size
            debug_timings["widget_resize_show_ms"] = (
                time.perf_counter() - resize_show_started
            ) * 1000.0

            store.viewport.geometry_state.pixmap_width = width
            store.viewport.geometry_state.pixmap_height = height
            store.viewport.geometry_state.image_display_rect_on_label = Rect(
                canvas_plan.padding_left,
                canvas_plan.padding_top,
                width,
                height,
            )

            configure_started = time.perf_counter()
            self._configure_widget_manual(
                widget,
                store,
                scene_images,
                canvas_plan,
                render_context,
                stroke_scales,
            )
            debug_timings["configure_widget_ms"] = (
                time.perf_counter() - configure_started
            ) * 1000.0

            paint_started = time.perf_counter()
            self._render_widget_frame(widget)
            debug_timings["paint_gl_ms"] = (
                time.perf_counter() - paint_started
            ) * 1000.0

            framebuffer_started = time.perf_counter()
            result_box["image"] = qimage_to_pil(widget.grabFramebuffer())
            debug_timings["grab_framebuffer_ms"] = (
                time.perf_counter() - framebuffer_started
            ) * 1000.0
            result_box["debug_timings"] = debug_timings
        except Exception as exc:
            logger.exception("GPU export rendering failed")
            result_box["error"] = exc
        finally:
            if viewport_state is not None and store is not None:
                self._restore_viewport_geometry(store, viewport_state)
            event.set()
