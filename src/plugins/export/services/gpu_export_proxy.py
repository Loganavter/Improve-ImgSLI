import logging
import threading
import time
from dataclasses import replace

from PIL import Image
from OpenGL import GL as gl
from PyQt6.QtCore import QObject, QPointF, Qt, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QColor, QImage
from PyQt6.QtWidgets import QApplication

from domain.types import Rect
from plugins.export.models import ExportRenderContext
from shared.regions import build_square_tile_grid, pad_image_to_size
from ui.canvas_features.capture.state import get_capture_widget_state
from ui.canvas_features.guides.state import get_guides_widget_state
from ui.canvas_features.magnifier.store import (
    active_or_default_border_color,
    active_or_default_divider_thickness,
    magnifier_enabled,
)
from ui.canvas_infra.scene.widget_registry import get_canvas_feature_command
from ui.widgets.gl_canvas import GLCanvas
from ui.canvas_infra.viewport.state import set_pan_offsets, set_zoom_level
from ui.widgets.gl_canvas.render import paint_gl
from ui.widgets.gl_canvas.scene import build_gl_render_scene

from .gpu_export_layout import (
    build_export_magnifier_layout,
    compute_canvas_plan,
    compute_export_stroke_scales,
    scale_export_stroke,
)

logger = logging.getLogger("ImproveImgSLI")

def _build_divider_export_overlay(
    store,
    *,
    scale_x: float,
    scale_y: float,
    content_offset_x: float,
    content_offset_y: float,
    content_width: float,
    content_height: float,
) -> dict:
    command = get_canvas_feature_command("divider", "export.overlay")
    if command is None:
        return {"visible": False, "split_pos": 0, "is_horizontal": False, "color": QColor(), "thickness": 0}
    return command(
        store,
        scale_x=scale_x,
        scale_y=scale_y,
        content_offset_x=content_offset_x,
        content_offset_y=content_offset_y,
        content_width=content_width,
        content_height=content_height,
    )

def qimage_to_pil(image: QImage) -> Image.Image:
    qimg = image.convertToFormat(QImage.Format.Format_RGBA8888)
    ptr = qimg.bits()
    ptr.setsize(qimg.sizeInBytes())
    return Image.frombytes("RGBA", (qimg.width(), qimg.height()), bytes(ptr))

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

    def _prepare_scene_images(
        self,
        render_context: ExportRenderContext,
        canvas_plan: dict,
    ):
        aligned_source1 = render_context.source_image1
        aligned_source2 = render_context.source_image2
        export_size = (
            getattr(render_context.image1, "size", None),
            getattr(render_context.image2, "size", None),
        )
        source_size = (
            getattr(aligned_source1, "size", None),
            getattr(aligned_source2, "size", None),
        )
        if source_size != export_size:
            aligned_source1 = render_context.image1
            aligned_source2 = render_context.image2
        cache_key = (
            render_context.source_key,
            id(render_context.image1) if render_context.image1 is not None else 0,
            id(render_context.image2) if render_context.image2 is not None else 0,
            id(aligned_source1) if aligned_source1 is not None else 0,
            id(aligned_source2) if aligned_source2 is not None else 0,
            id(render_context.cached_diff_image) if render_context.cached_diff_image is not None else 0,
            int(canvas_plan["canvas_width"]),
            int(canvas_plan["canvas_height"]),
            int(canvas_plan["padding_left"]),
            int(canvas_plan["padding_top"]),
        )
        cached = self._scene_images_cache.get(cache_key)
        if cached is not None:
            return cached

        bg1, bg2 = render_context.prepared_background_layers or (
            render_context.image1,
            render_context.image2,
        )
        diff_image = render_context.cached_diff_image

        canvas_w = canvas_plan["canvas_width"]
        canvas_h = canvas_plan["canvas_height"]
        pad_left = canvas_plan["padding_left"]
        pad_top = canvas_plan["padding_top"]

        def pad(image: Image.Image | None):
            if image is None:
                return None
            result = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
            result.paste(image.convert("RGBA"), (pad_left, pad_top))
            return result

        scene_images = {
            "bg1": pad(bg1),
            "bg2": pad(bg2),
            "src1": pad(aligned_source1),
            "src2": pad(aligned_source2),
            "diff": pad(diff_image) if diff_image is not None else None,
        }
        if len(self._scene_images_cache) >= 8:
            self._scene_images_cache.clear()
        self._scene_images_cache[cache_key] = scene_images
        return scene_images

    def _configure_widget_manual(
        self,
        widget,
        store,
        scene_images: dict,
        canvas_plan: dict,
        render_context: ExportRenderContext,
        stroke_scales: tuple[float, float, float],
    ):
        vp = store.viewport
        view = vp.view_state
        render = vp.render_config
        capture_state = get_capture_widget_state(view)
        guides_state = get_guides_widget_state(view)
        scale_x, scale_y, scale_ref = stroke_scales
        image_w = canvas_plan["image_width"]
        image_h = canvas_plan["image_height"]
        canvas_w = canvas_plan["canvas_width"]
        canvas_h = canvas_plan["canvas_height"]
        pad_left = canvas_plan["padding_left"]
        pad_top = canvas_plan["padding_top"]

        widget.configure_offscreen_render(
            stored_images=(scene_images["bg1"], scene_images["bg2"]),
            source_images=(scene_images["src1"], scene_images["src2"]),
            content_rect=(pad_left, pad_top, image_w, image_h),
            shader_letterbox=False,
        )
        divider_overlay = _build_divider_export_overlay(
            store,
            scale_x=scale_x,
            scale_y=scale_y,
            content_offset_x=pad_left,
            content_offset_y=pad_top,
            content_width=image_w,
            content_height=image_h,
        )
        divider_thickness_export = int(divider_overlay.get("thickness", 0))
        guides_thickness_export = scale_export_stroke(
            guides_state.thickness,
            scale_ref,
        )
        magnifier_divider_thickness_export = scale_export_stroke(
            active_or_default_divider_thickness(view),
            scale_ref,
        )
        scene = build_gl_render_scene(
            store,
            apply_channel_mode_in_shader=False,
            clip_overlays_to_image_bounds=False,
        )
        scene = replace(
            scene,
            divider_thickness=divider_thickness_export,
            filename_overlay=replace(
                scene.filename_overlay,
                divider_thickness=divider_thickness_export,
            ),
        )
        widget.set_render_scene(scene)
        set_zoom_level(widget, 1.0)
        set_pan_offsets(widget, 0.0, 0.0)
        widget.is_horizontal = view.is_horizontal
        widget.set_apply_channel_mode_in_shader(False)
        if scene_images["diff"] is not None:
            widget.upload_diff_source_pil_image(scene_images["diff"])
        else:
            widget.upload_diff_source_pil_image(None)

        widget.set_split_line_params(
            bool(divider_overlay.get("visible", False)),
            int(divider_overlay.get("split_pos", 0)),
            bool(divider_overlay.get("is_horizontal", False)),
            divider_overlay.get("color", QColor()),
            divider_thickness_export,
        )
        widget.set_guides_params(
            guides_state.enabled,
            QColor(guides_state.color.r, guides_state.color.g, guides_state.color.b, guides_state.color.a),
            guides_thickness_export,
        )
        widget.set_capture_color(QColor(capture_state.color.r, capture_state.color.g, capture_state.color.b, capture_state.color.a))

        magnifier_layout = build_export_magnifier_layout(
            vp,
            width=image_w,
            height=image_h,
            canvas_width=canvas_w,
            canvas_height=canvas_h,
            content_offset_x=pad_left,
            content_offset_y=pad_top,
            divider_thickness_px=magnifier_divider_thickness_export,
            render_scale=1.0,
        )
        slots = magnifier_layout["slots"]
        mag_centers = [slot["center"] for slot in slots]
        capture_center = magnifier_layout["capture_center"]
        cap_radius = magnifier_layout["capture_radius"]
        capture_circles = magnifier_layout.get("capture_circles", [])
        guide_sets = magnifier_layout.get("guide_sets", [])
        mag_radius = magnifier_layout["mag_radius"]
        channel_mode_int = magnifier_layout["channel_mode_int"]
        interp_mode_int = magnifier_layout["interp_mode_int"]
        diff_mode_int = magnifier_layout["diff_mode_int"]

        widget.set_overlay_coords(
            capture_center if capture_state.visible else None,
            cap_radius if capture_state.visible else 0.0,
            mag_centers,
            mag_radius,
        )
        runtime_state = getattr(widget, "runtime_state", None)
        if runtime_state is not None:
            runtime_state._capture_circles = list(capture_circles)
            runtime_state._guide_sets = list(guide_sets)
        if magnifier_enabled(view):
            widget.set_magnifier_gpu_params(
                slots,
                channel_mode_int,
                4 if view.diff_mode == "ssim" and scene_images["diff"] is not None else diff_mode_int,
                20.0 / 255.0,
                QColor(
                    active_or_default_border_color(view).r,
                    active_or_default_border_color(view).g,
                    active_or_default_border_color(view).b,
                    active_or_default_border_color(view).a,
                ),
                2.0,
                interp_mode_int,
            )
        else:
            widget.clear_magnifier_gpu()

    def _render_tiled_image(
        self,
        widget,
        store,
        render_context: ExportRenderContext,
        width: int,
        height: int,
        prepared_background_layers=None,
        min_tiles_per_axis: int = 2,
        stroke_scales: tuple[float, float, float] = (1.0, 1.0, 1.0),
    ) -> Image.Image:
        if store.viewport.render_config.include_file_names_in_saved:
            raise RuntimeError("Tiled GPU export does not support filename overlay yet")

        max_tex = self._get_max_texture_size(widget)
        tile_grid = build_square_tile_grid(
            width,
            height,
            max_tile_extent=max_tex,
            min_tiles_per_axis=min_tiles_per_axis,
        )
        tile_debug = {
            "tile_columns": float(tile_grid.columns),
            "tile_rows": float(tile_grid.rows),
            "tile_width": float(tile_grid.tile_width),
            "tile_height": float(tile_grid.tile_height),
        }
        tile_w = tile_grid.tile_width
        tile_h = tile_grid.tile_height
        padded_w = tile_grid.padded_width
        padded_h = tile_grid.padded_height

        image1 = render_context.image1
        image2 = render_context.image2
        bg1, bg2 = prepared_background_layers or (image1, image2)
        bg1 = pad_image_to_size(bg1.convert("RGBA"), padded_w, padded_h)
        bg2 = pad_image_to_size(bg2.convert("RGBA"), padded_w, padded_h)
        src1 = pad_image_to_size(image1.convert("RGBA"), padded_w, padded_h)
        src2 = pad_image_to_size(image2.convert("RGBA"), padded_w, padded_h)

        diff_mode = str(store.viewport.view_state.diff_mode or "off")
        diff_image = render_context.cached_diff_image
        if diff_image is not None:
            diff_image = pad_image_to_size(diff_image.convert("RGBA"), padded_w, padded_h)

        final_image = Image.new("RGBA", (padded_w, padded_h), (0, 0, 0, 0))

        vp = store.viewport
        view = vp.view_state
        render = vp.render_config
        capture_state = get_capture_widget_state(view)
        guides_state = get_guides_widget_state(view)
        scale_x, scale_y, scale_ref = stroke_scales
        divider_overlay = _build_divider_export_overlay(
            store,
            scale_x=scale_x,
            scale_y=scale_y,
            content_offset_x=0,
            content_offset_y=0,
            content_width=tile_w,
            content_height=tile_h,
        )
        divider_thickness_export = int(divider_overlay.get("thickness", 0))
        guides_thickness_export = scale_export_stroke(
            guides_state.thickness,
            scale_ref,
        )
        magnifier_divider_thickness_export = scale_export_stroke(
            active_or_default_divider_thickness(view),
            scale_ref,
        )
        border = active_or_default_border_color(view)
        border_color = QColor(border.r, border.g, border.b, border.a)
        capture_color = QColor(capture_state.color.r, capture_state.color.g, capture_state.color.b, capture_state.color.a)
        laser_color = QColor(guides_state.color.r, guides_state.color.g, guides_state.color.b, guides_state.color.a)
        scene = build_gl_render_scene(
            store,
            apply_channel_mode_in_shader=False,
            clip_overlays_to_image_bounds=False,
        )
        scene = replace(
            scene,
            divider_thickness=divider_thickness_export,
            filename_overlay=replace(
                scene.filename_overlay,
                divider_thickness=divider_thickness_export,
            ),
        )
        widget.set_render_scene(scene)
        render_scale = float(tile_grid.columns)
        global_canvas_plan = compute_canvas_plan(
            store,
            width,
            height,
            magnifier_drawing_coords=render_context.magnifier_drawing_coords,
        )
        magnifier_layout = build_export_magnifier_layout(
            vp,
            width=width,
            height=height,
            canvas_width=padded_w,
            canvas_height=padded_h,
            content_offset_x=global_canvas_plan["padding_left"],
            content_offset_y=global_canvas_plan["padding_top"],
            divider_thickness_px=magnifier_divider_thickness_export,
            render_scale=render_scale,
        )
        slots = magnifier_layout["slots"]
        magnifier_centers = magnifier_layout["magnifier_centers"]
        capture_center = magnifier_layout["capture_center"]
        cap_radius = magnifier_layout["capture_radius"]
        mag_radius = magnifier_layout["mag_radius"]
        channel_mode_int = magnifier_layout["channel_mode_int"]
        interp_mode_int = magnifier_layout["interp_mode_int"]
        diff_mode_int = magnifier_layout["diff_mode_int"]

        def to_local_point(x: float, y: float) -> tuple[float, float]:
            return (
                (x / render_scale) - (tile_left / render_scale),
                (y / render_scale) - (tile_top / render_scale),
            )

        def to_local_radius(radius: float) -> float:
            return radius / render_scale

        tile_resize_show_total = 0.0
        tile_paint_total = 0.0
        tile_grab_total = 0.0
        tile_paste_total = 0.0
        for _row, _col, tile_region in tile_grid.iter_regions():
            tile_left = tile_region.left
            tile_top = tile_region.top
            actual_w = tile_region.width
            actual_h = tile_region.height

            resize_show_started = time.perf_counter()
            widget.resize(tile_w, tile_h)
            widget.show()
            QApplication.processEvents()
            tile_resize_show_total += (time.perf_counter() - resize_show_started) * 1000.0

            widget.configure_offscreen_render(
                stored_images=(bg1, bg2),
                source_images=(src1, src2),
                content_rect=(0, 0, tile_w, tile_h),
                shader_letterbox=False,
            )
            set_zoom_level(widget, render_scale)
            set_pan_offsets(
                widget,
                0.5 - ((tile_left + (tile_w / 2.0)) / padded_w),
                0.5 - ((tile_top + (tile_h / 2.0)) / padded_h),
            )
            widget.set_apply_channel_mode_in_shader(False)
            if diff_image is not None:
                widget.upload_diff_source_pil_image(diff_image)
            else:
                widget.upload_diff_source_pil_image(None)

            widget.set_split_line_params(
                bool(divider_overlay.get("visible", False)),
                int(divider_overlay.get("split_pos", 0)),
                bool(divider_overlay.get("is_horizontal", False)),
                divider_overlay.get("color", QColor()),
                divider_thickness_export,
            )
            widget.set_guides_params(
                guides_state.enabled,
                laser_color,
                guides_thickness_export,
            )
            widget.set_capture_color(capture_color)

            capture_center_local = None
            if capture_state.visible and capture_center is not None:
                cap_local_x, cap_local_y = to_local_point(
                    capture_center.x() * render_scale,
                    capture_center.y() * render_scale,
                )
                capture_center_local = QPointF(cap_local_x, cap_local_y)

            mag_center_points = [
                QPointF(x / render_scale, y / render_scale)
                for x, y in magnifier_centers
            ]
            widget.set_overlay_coords(
                capture_center_local,
                to_local_radius(cap_radius) if capture_center_local is not None else 0.0,
                mag_center_points,
                to_local_radius(mag_radius),
            )
            runtime_state = getattr(widget, "runtime_state", None)
            if runtime_state is not None:
                runtime_state._capture_circles = [
                    (
                        QPointF(
                            *to_local_point(center.x() * render_scale, center.y() * render_scale)
                        ),
                        to_local_radius(radius),
                        color,
                    )
                    for center, radius, color in capture_circles
                ]
                runtime_state._guide_sets = []
                for capture_center_item, capture_radius_item, target_centers_item, target_radius_item, color_item in guide_sets:
                    target_radius_local = (
                        tuple(to_local_radius(radius) for radius in target_radius_item)
                        if isinstance(target_radius_item, (tuple, list))
                        else to_local_radius(target_radius_item)
                    )
                    runtime_state._guide_sets.append(
                        (
                            QPointF(
                                *to_local_point(capture_center_item.x() * render_scale, capture_center_item.y() * render_scale)
                            ),
                            to_local_radius(capture_radius_item),
                            [
                                QPointF(*to_local_point(center.x() * render_scale, center.y() * render_scale))
                                for center in target_centers_item
                            ],
                            target_radius_local,
                            color_item,
                        )
                    )
            if magnifier_enabled(view):
                widget.set_magnifier_gpu_params(
                    slots,
                    channel_mode_int,
                    4 if diff_mode == "ssim" and diff_image is not None else {"off": 0, "highlight": 1, "grayscale": 2, "edges": 3, "ssim": 4}.get(diff_mode, 0),
                    20.0 / 255.0,
                    border_color,
                    2.0,
                    interp_mode_int,
                )
            else:
                widget.clear_magnifier_gpu()

            paint_started = time.perf_counter()
            self._render_widget_frame(widget)
            tile_paint_total += (time.perf_counter() - paint_started) * 1000.0

            grab_started = time.perf_counter()
            tile_img = qimage_to_pil(widget.grabFramebuffer())
            tile_grab_total += (time.perf_counter() - grab_started) * 1000.0

            paste_started = time.perf_counter()
            final_image.paste(tile_img.crop((0, 0, actual_w, actual_h)), (tile_left, tile_top))
            tile_paste_total += (time.perf_counter() - paste_started) * 1000.0

        tile_debug["tile_resize_show_ms"] = tile_resize_show_total
        tile_debug["tile_paint_ms"] = tile_paint_total
        tile_debug["tile_grab_ms"] = tile_grab_total
        tile_debug["tile_paste_ms"] = tile_paste_total
        self._last_tiled_debug = tile_debug
        return final_image.crop((0, 0, width, height))

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
                    magnifier_drawing_coords=payload.get("magnifier_drawing_coords"),
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
                result_box["image"] = self._render_tiled_image(
                    widget,
                    store,
                    render_context,
                    width,
                    height,
                    prepared_background_layers=render_context.prepared_background_layers,
                    min_tiles_per_axis=min_tiles_per_axis,
                    stroke_scales=stroke_scales,
                )
                debug_timings["tiled_total_ms"] = (
                    time.perf_counter() - tiled_started
                ) * 1000.0
                debug_timings["tiled_min_tiles_per_axis"] = float(min_tiles_per_axis)
                debug_timings.update(getattr(self, "_last_tiled_debug", {}) or {})
                result_box["debug_timings"] = debug_timings
                return

            canvas_started = time.perf_counter()
            canvas_plan = compute_canvas_plan(
                store,
                width,
                height,
                magnifier_drawing_coords=render_context.magnifier_drawing_coords,
            )
            debug_timings["canvas_plan_ms"] = (
                time.perf_counter() - canvas_started
            ) * 1000.0
            canvas_w = canvas_plan["canvas_width"]
            canvas_h = canvas_plan["canvas_height"]

            prepare_started = time.perf_counter()
            scene_images = self._prepare_scene_images(
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
                canvas_plan["padding_left"],
                canvas_plan["padding_top"],
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
