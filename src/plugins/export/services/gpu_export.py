import logging
import math
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
from ui.widgets.gl_canvas.render import paint_gl
from ui.widgets.gl_canvas.scene import build_gl_render_scene
from ui.widgets.gl_canvas.widget import GLCanvas
from utils.resource_loader import get_magnifier_drawing_coords

logger = logging.getLogger("ImproveImgSLI")

def _qimage_to_pil(image: QImage) -> Image.Image:
    qimg = image.convertToFormat(QImage.Format.Format_RGBA8888)
    ptr = qimg.bits()
    ptr.setsize(qimg.sizeInBytes())
    return Image.frombytes("RGBA", (qimg.width(), qimg.height()), bytes(ptr))

def _clamp_capture_position(rel_x: float, rel_y: float, width: int, height: int, capture_size: float):
    radius_x = (capture_size * min(width, height) / 2.0) / max(1.0, float(width))
    radius_y = (capture_size * min(width, height) / 2.0) / max(1.0, float(height))
    return (
        max(radius_x, min(rel_x, 1.0 - radius_x)),
        max(radius_y, min(rel_y, 1.0 - radius_y)),
    )

def _compute_canvas_plan(store, image_width: int, image_height: int, magnifier_drawing_coords=None) -> dict:
    magnifier_coords = magnifier_drawing_coords
    if magnifier_coords is None and getattr(store.viewport.view_state, "use_magnifier", False):
        magnifier_coords = get_magnifier_drawing_coords(
            store=store,
            drawing_width=image_width,
            drawing_height=image_height,
            container_width=image_width,
            container_height=image_height,
        )

    pad_left = 0
    pad_top = 0
    pad_right = 0
    pad_bottom = 0
    bbox = None
    if magnifier_coords and len(magnifier_coords) > 5:
        bbox = magnifier_coords[5]
    if bbox is not None and hasattr(bbox, "isValid") and bbox.isValid():
        pad_left = abs(min(0, bbox.left()))
        pad_top = abs(min(0, bbox.top()))
        pad_right = max(0, bbox.right() - image_width)
        pad_bottom = max(0, bbox.bottom() - image_height)

    return {
        "image_width": image_width,
        "image_height": image_height,
        "canvas_width": image_width + pad_left + pad_right,
        "canvas_height": image_height + pad_top + pad_bottom,
        "padding_left": pad_left,
        "padding_top": pad_top,
        "padding_right": pad_right,
        "padding_bottom": pad_bottom,
        "magnifier_coords": magnifier_coords,
    }

def _get_divider_color_tuple(vp):
    color = getattr(vp.render_config, "magnifier_divider_color", None)
    if color is None:
        return (1.0, 1.0, 1.0, 0.9)
    return (
        color.r / 255.0,
        color.g / 255.0,
        color.b / 255.0,
        color.a / 255.0,
    )

def _scale_export_stroke(value: int, scale: float) -> int:
    if value <= 0:
        return 0
    return max(1, int(round(float(value) * max(1.0, float(scale)))))

def _compute_export_stroke_scales(viewport_state: dict | None, width: int, height: int) -> tuple[float, float, float]:
    if not viewport_state:
        return 1.0, 1.0, 1.0
    display_w = max(1, int(viewport_state.get("pixmap_width", 0) or 0))
    display_h = max(1, int(viewport_state.get("pixmap_height", 0) or 0))
    scale_x = float(width) / float(display_w) if display_w > 0 else 1.0
    scale_y = float(height) / float(display_h) if display_h > 0 else 1.0
    return scale_x, scale_y, min(scale_x, scale_y)

class _GpuExportProxy(QObject):
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
        widget.makeCurrent()
        try:
            value = int(gl.glGetIntegerv(gl.GL_MAX_TEXTURE_SIZE))
        finally:
            widget.doneCurrent()
        return max(1, value)

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
        divider_thickness_export = _scale_export_stroke(
            render.divider_line_thickness,
            scale_y if view.is_horizontal else scale_x,
        )
        guides_thickness_export = _scale_export_stroke(
            render.magnifier_guides_thickness,
            scale_ref,
        )
        magnifier_divider_thickness_export = _scale_export_stroke(
            render.magnifier_divider_thickness,
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
        widget.zoom_level = 1.0
        widget.pan_offset_x = 0.0
        widget.pan_offset_y = 0.0
        widget.is_horizontal = view.is_horizontal
        widget.set_apply_channel_mode_in_shader(False)
        if scene_images["diff"] is not None:
            widget.upload_diff_source_pil_image(scene_images["diff"])
        else:
            widget.upload_diff_source_pil_image(None)

        split_pos_local = int(
            round(
                (pad_top + (image_h * view.split_position_visual))
                if view.is_horizontal
                else (pad_left + (image_w * view.split_position_visual))
            )
        )
        widget.set_split_line_params(
            render.divider_line_visible and view.diff_mode == "off",
            split_pos_local,
            view.is_horizontal,
            QColor(
                render.divider_line_color.r,
                render.divider_line_color.g,
                render.divider_line_color.b,
                render.divider_line_color.a,
            ),
            divider_thickness_export,
        )
        widget.set_guides_params(
            render.show_magnifier_guides,
            QColor(
                render.magnifier_laser_color.r,
                render.magnifier_laser_color.g,
                render.magnifier_laser_color.b,
                render.magnifier_laser_color.a,
            ),
            guides_thickness_export,
        )
        widget.set_capture_color(
            QColor(
                render.capture_ring_color.r,
                render.capture_ring_color.g,
                render.capture_ring_color.b,
                render.capture_ring_color.a,
            )
        )

        magnifier_coords = render_context.magnifier_drawing_coords
        capture_center = (
            magnifier_coords[6]
            if magnifier_coords is not None and len(magnifier_coords) > 6
            else None
        )
        if capture_center is not None:
            clamped_x = float(capture_center.x()) / max(1.0, float(image_w))
            clamped_y = float(capture_center.y()) / max(1.0, float(image_h))
        else:
            clamped_x, clamped_y = _clamp_capture_position(
                view.capture_position_relative.x,
                view.capture_position_relative.y,
                image_w,
                image_h,
                view.capture_size_relative,
            )
        target_max = float(max(image_w, image_h))
        capture_ref = float(min(image_w, image_h))
        cap_center_x = pad_left + (clamped_x * image_w)
        cap_center_y = pad_top + (clamped_y * image_h)
        cap_radius = (view.capture_size_relative * capture_ref) / 2.0
        if magnifier_coords is not None and len(magnifier_coords) > 3:
            mag_radius = float(magnifier_coords[3]) / 2.0
        else:
            mag_radius = (view.magnifier_size_relative * target_max) / 2.0
        if magnifier_coords is not None and len(magnifier_coords) > 4:
            spacing_px = float(magnifier_coords[4])
        else:
            spacing_px = view.magnifier_spacing_relative_visual * target_max

        if magnifier_coords is not None and len(magnifier_coords) > 2 and magnifier_coords[2] is not None:
            base_x = pad_left + float(magnifier_coords[2].x())
            base_y = pad_top + float(magnifier_coords[2].y())
        elif view.freeze_magnifier and view.frozen_capture_point_relative is not None:
            frozen_x, frozen_y = _clamp_capture_position(
                view.frozen_capture_point_relative.x,
                view.frozen_capture_point_relative.y,
                image_w,
                image_h,
                view.capture_size_relative,
            )
            base_x = pad_left + frozen_x * image_w
            base_y = pad_top + frozen_y * image_h
        else:
            base_x = cap_center_x
            base_y = cap_center_y

        mag_center_x = base_x
        mag_center_y = base_y
        is_visual_diff = (
            view.diff_mode in ("highlight", "grayscale", "ssim", "edges")
            and view.magnifier_visible_center
        )
        channel_mode_int = {"RGB": 0, "R": 1, "G": 2, "B": 3, "L": 4}.get(
            view.channel_view_mode,
            0,
        )
        interp_key = str(render.interpolation_method or "BILINEAR").upper()
        interp_mode_int = {
            "NEAREST": 0,
            "BILINEAR": 1,
            "BICUBIC": 2,
            "LANCZOS": 3,
            "EWA_LANCZOS": 4,
        }.get(interp_key, 1)
        cap_half_w = (view.capture_size_relative * capture_ref / 2.0) / max(1.0, float(canvas_w))
        cap_half_h = (view.capture_size_relative * capture_ref / 2.0) / max(1.0, float(canvas_h))
        uv_rect = (
            (cap_center_x / canvas_w) - cap_half_w,
            (cap_center_y / canvas_h) - cap_half_h,
            (cap_center_x / canvas_w) + cap_half_w,
            (cap_center_y / canvas_h) + cap_half_h,
        )
        div_color_t = (
            render.magnifier_divider_color.r / 255.0,
            render.magnifier_divider_color.g / 255.0,
            render.magnifier_divider_color.b / 255.0,
            render.magnifier_divider_color.a / 255.0,
        )

        def make_slot(x, y, source, is_combined=False):
            mag_px = max(1.0, mag_radius * 2.0)
            return {
                "center": QPointF(x, y),
                "radius": mag_radius,
                "uv_rect": uv_rect,
                "uv_rect2": uv_rect,
                "source": source,
                "is_combined": is_combined,
                "internal_split": view.magnifier_internal_split,
                "horizontal": view.magnifier_is_horizontal,
                "divider_visible": render.magnifier_divider_visible,
                "divider_color": div_color_t,
                "divider_thickness_px": magnifier_divider_thickness_export,
                "divider_thickness_uv": (magnifier_divider_thickness_export / mag_px) * 0.5,
            }

        slots = [None, None, None]
        mag_centers = []
        if view.use_magnifier:
            if view.is_magnifier_combined:
                if is_visual_diff:
                    if not view.magnifier_is_horizontal:
                        diff_center = (mag_center_x, mag_center_y - mag_radius - 4.0)
                        comb_center = (mag_center_x, mag_center_y + mag_radius + 4.0)
                    else:
                        diff_center = (mag_center_x - mag_radius - 4.0, mag_center_y)
                        comb_center = (mag_center_x + mag_radius + 4.0, mag_center_y)
                    if view.magnifier_visible_center:
                        slots[0] = make_slot(*diff_center, 2)
                        mag_centers.append(QPointF(*diff_center))
                    if view.magnifier_visible_left and view.magnifier_visible_right:
                        slots[1] = make_slot(*comb_center, 0, is_combined=True)
                        mag_centers.append(QPointF(*comb_center))
                    elif view.magnifier_visible_left:
                        slots[1] = make_slot(*comb_center, 0)
                        mag_centers.append(QPointF(*comb_center))
                    elif view.magnifier_visible_right:
                        slots[1] = make_slot(*comb_center, 1)
                        mag_centers.append(QPointF(*comb_center))
                else:
                    if view.magnifier_visible_left and view.magnifier_visible_right:
                        slots[0] = make_slot(mag_center_x, mag_center_y, 0, is_combined=True)
                        mag_centers.append(QPointF(mag_center_x, mag_center_y))
                    elif view.magnifier_visible_left:
                        slots[0] = make_slot(mag_center_x, mag_center_y, 0)
                        mag_centers.append(QPointF(mag_center_x, mag_center_y))
                    elif view.magnifier_visible_right:
                        slots[0] = make_slot(mag_center_x, mag_center_y, 1)
                        mag_centers.append(QPointF(mag_center_x, mag_center_y))
            elif is_visual_diff:
                offset_3 = max(mag_radius * 2.0, mag_radius * 2.0 + spacing_px)
                if not view.magnifier_is_horizontal:
                    left_center = (mag_center_x - offset_3, mag_center_y)
                    right_center = (mag_center_x + offset_3, mag_center_y)
                else:
                    left_center = (mag_center_x, mag_center_y - offset_3)
                    right_center = (mag_center_x, mag_center_y + offset_3)
                if view.magnifier_visible_left:
                    slots[0] = make_slot(*left_center, 0)
                    mag_centers.append(QPointF(*left_center))
                if view.magnifier_visible_right:
                    slots[1] = make_slot(*right_center, 1)
                    mag_centers.append(QPointF(*right_center))
                if view.magnifier_visible_center:
                    slots[2] = make_slot(mag_center_x, mag_center_y, 2)
                    mag_centers.append(QPointF(mag_center_x, mag_center_y))
            else:
                dist = mag_radius + (spacing_px / 2.0)
                if not view.magnifier_is_horizontal:
                    left_center = (mag_center_x - dist, mag_center_y)
                    right_center = (mag_center_x + dist, mag_center_y)
                else:
                    left_center = (mag_center_x, mag_center_y - dist)
                    right_center = (mag_center_x, mag_center_y + dist)
                if view.magnifier_visible_left and view.magnifier_visible_right:
                    slots[0] = make_slot(*left_center, 0)
                    slots[1] = make_slot(*right_center, 1)
                    mag_centers.extend([QPointF(*left_center), QPointF(*right_center)])
                elif view.magnifier_visible_left:
                    slots[0] = make_slot(mag_center_x, mag_center_y, 0)
                    mag_centers.append(QPointF(mag_center_x, mag_center_y))
                elif view.magnifier_visible_right:
                    slots[0] = make_slot(mag_center_x, mag_center_y, 1)
                    mag_centers.append(QPointF(mag_center_x, mag_center_y))

        widget.set_overlay_coords(
            QPointF(cap_center_x, cap_center_y)
            if render.show_capture_area_on_main_image
            else None,
            cap_radius if render.show_capture_area_on_main_image else 0.0,
            mag_centers,
            mag_radius,
        )
        if view.use_magnifier:
            widget.set_magnifier_gpu_params(
                slots,
                channel_mode_int,
                4 if view.diff_mode == "ssim" and scene_images["diff"] is not None else {"off": 0, "highlight": 1, "grayscale": 2, "edges": 3, "ssim": 4}.get(view.diff_mode, 0),
                20.0 / 255.0,
                QColor(
                    render.magnifier_border_color.r,
                    render.magnifier_border_color.g,
                    render.magnifier_border_color.b,
                    render.magnifier_border_color.a,
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
        scale_x, scale_y, scale_ref = stroke_scales
        divider_thickness_export = _scale_export_stroke(
            render.divider_line_thickness,
            scale_y if view.is_horizontal else scale_x,
        )
        guides_thickness_export = _scale_export_stroke(
            render.magnifier_guides_thickness,
            scale_ref,
        )
        magnifier_divider_thickness_export = _scale_export_stroke(
            render.magnifier_divider_thickness,
            scale_ref,
        )
        split_color = QColor(
            render.divider_line_color.r,
            render.divider_line_color.g,
            render.divider_line_color.b,
            render.divider_line_color.a,
        )
        border_color = QColor(
            render.magnifier_border_color.r,
            render.magnifier_border_color.g,
            render.magnifier_border_color.b,
            render.magnifier_border_color.a,
        )
        capture_color = QColor(
            render.capture_ring_color.r,
            render.capture_ring_color.g,
            render.capture_ring_color.b,
            render.capture_ring_color.a,
        )
        laser_color = QColor(
            render.magnifier_laser_color.r,
            render.magnifier_laser_color.g,
            render.magnifier_laser_color.b,
            render.magnifier_laser_color.a,
        )
        div_color_t = _get_divider_color_tuple(vp)
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
        magnifier_coords = render_context.magnifier_drawing_coords
        capture_center = (
            magnifier_coords[6]
            if magnifier_coords is not None and len(magnifier_coords) > 6
            else None
        )
        if capture_center is not None:
            clamped_x = float(capture_center.x()) / max(1.0, float(width))
            clamped_y = float(capture_center.y()) / max(1.0, float(height))
        else:
            clamped_x, clamped_y = _clamp_capture_position(
                view.capture_position_relative.x,
                view.capture_position_relative.y,
                width,
                height,
                view.capture_size_relative,
            )
        target_max = float(max(width, height))
        capture_ref = float(min(width, height))
        cap_center_x = clamped_x * width
        cap_center_y = clamped_y * height
        cap_radius = (view.capture_size_relative * capture_ref) / 2.0
        if magnifier_coords is not None and len(magnifier_coords) > 3:
            mag_radius = float(magnifier_coords[3]) / 2.0
        else:
            mag_radius = (view.magnifier_size_relative * target_max) / 2.0

        if magnifier_coords is not None and len(magnifier_coords) > 2 and magnifier_coords[2] is not None:
            base_x = float(magnifier_coords[2].x())
            base_y = float(magnifier_coords[2].y())
        elif view.freeze_magnifier and view.frozen_capture_point_relative is not None:
            frozen_x, frozen_y = _clamp_capture_position(
                view.frozen_capture_point_relative.x,
                view.frozen_capture_point_relative.y,
                width,
                height,
                view.capture_size_relative,
            )
            base_x = frozen_x * width
            base_y = frozen_y * height
        else:
            base_x = cap_center_x
            base_y = cap_center_y

        mag_center_x = base_x
        mag_center_y = base_y
        if magnifier_coords is not None and len(magnifier_coords) > 4:
            spacing_px = float(magnifier_coords[4])
        else:
            spacing_px = view.magnifier_spacing_relative_visual * target_max
        is_visual_diff = diff_mode in ("highlight", "grayscale", "ssim", "edges") and view.magnifier_visible_center
        channel_mode_int = {"RGB": 0, "R": 1, "G": 2, "B": 3, "L": 4}.get(view.channel_view_mode, 0)
        interp_key = str(render.interpolation_method or "BILINEAR").upper()
        interp_mode_int = {
            "NEAREST": 0,
            "BILINEAR": 1,
            "BICUBIC": 2,
            "LANCZOS": 3,
            "EWA_LANCZOS": 4,
        }.get(interp_key, 1)
        cap_half_w = (view.capture_size_relative * capture_ref / 2.0) / max(1.0, float(padded_w))
        cap_half_h = (view.capture_size_relative * capture_ref / 2.0) / max(1.0, float(padded_h))
        uv_rect = (
            (cap_center_x / padded_w) - cap_half_w,
            (cap_center_y / padded_h) - cap_half_h,
            (cap_center_x / padded_w) + cap_half_w,
            (cap_center_y / padded_h) + cap_half_h,
        )

        render_scale = float(tile_grid.columns)

        def to_local_point(x: float, y: float):
            return x / render_scale, y / render_scale

        def to_local_radius(radius_value: float):
            return radius_value / render_scale

        def make_slot(center_xy, source, is_combined=False):
            local_x, local_y = to_local_point(*center_xy)
            local_radius = to_local_radius(mag_radius)
            local_mag_px = max(1.0, local_radius * 2.0)
            return {
                "center": QPointF(local_x, local_y),
                "radius": local_radius,
                "uv_rect": uv_rect,
                "uv_rect2": uv_rect,
                "source": source,
                "is_combined": is_combined,
                "internal_split": view.magnifier_internal_split,
                "horizontal": view.magnifier_is_horizontal,
                "divider_visible": render.magnifier_divider_visible,
                "divider_color": div_color_t,
                "divider_thickness_px": magnifier_divider_thickness_export,
                "divider_thickness_uv": (magnifier_divider_thickness_export / local_mag_px) * 0.5,
            }

        slots = [None, None, None]
        magnifier_centers = []
        if view.use_magnifier:
            if view.is_magnifier_combined:
                if is_visual_diff:
                    if not view.magnifier_is_horizontal:
                        diff_center = (mag_center_x, mag_center_y - mag_radius - 4.0)
                        comb_center = (mag_center_x, mag_center_y + mag_radius + 4.0)
                    else:
                        diff_center = (mag_center_x - mag_radius - 4.0, mag_center_y)
                        comb_center = (mag_center_x + mag_radius + 4.0, mag_center_y)
                    if view.magnifier_visible_center:
                        slots[0] = make_slot(diff_center, 2)
                        magnifier_centers.append(diff_center)
                    if view.magnifier_visible_left and view.magnifier_visible_right:
                        slots[1] = make_slot(comb_center, 0, is_combined=True)
                        magnifier_centers.append(comb_center)
                    elif view.magnifier_visible_left:
                        slots[1] = make_slot(comb_center, 0)
                        magnifier_centers.append(comb_center)
                    elif view.magnifier_visible_right:
                        slots[1] = make_slot(comb_center, 1)
                        magnifier_centers.append(comb_center)
                else:
                    center = (mag_center_x, mag_center_y)
                    if view.magnifier_visible_left and view.magnifier_visible_right:
                        slots[0] = make_slot(center, 0, is_combined=True)
                        magnifier_centers.append(center)
                    elif view.magnifier_visible_left:
                        slots[0] = make_slot(center, 0)
                        magnifier_centers.append(center)
                    elif view.magnifier_visible_right:
                        slots[0] = make_slot(center, 1)
                        magnifier_centers.append(center)
            elif is_visual_diff:
                offset_3 = max(mag_radius * 2.0, mag_radius * 2.0 + spacing_px)
                if not view.magnifier_is_horizontal:
                    left_center = (mag_center_x - offset_3, mag_center_y)
                    right_center = (mag_center_x + offset_3, mag_center_y)
                else:
                    left_center = (mag_center_x, mag_center_y - offset_3)
                    right_center = (mag_center_x, mag_center_y + offset_3)
                if view.magnifier_visible_left:
                    slots[0] = make_slot(left_center, 0)
                    magnifier_centers.append(left_center)
                if view.magnifier_visible_right:
                    slots[1] = make_slot(right_center, 1)
                    magnifier_centers.append(right_center)
                if view.magnifier_visible_center:
                    center = (mag_center_x, mag_center_y)
                    slots[2] = make_slot(center, 2)
                    magnifier_centers.append(center)
            else:
                dist = mag_radius + (spacing_px / 2.0)
                if not view.magnifier_is_horizontal:
                    left_center = (mag_center_x - dist, mag_center_y)
                    right_center = (mag_center_x + dist, mag_center_y)
                else:
                    left_center = (mag_center_x, mag_center_y - dist)
                    right_center = (mag_center_x, mag_center_y + dist)
                if view.magnifier_visible_left and view.magnifier_visible_right:
                    slots[0] = make_slot(left_center, 0)
                    slots[1] = make_slot(right_center, 1)
                    magnifier_centers.extend([left_center, right_center])
                elif view.magnifier_visible_left:
                    slots[0] = make_slot((mag_center_x, mag_center_y), 0)
                    magnifier_centers.append((mag_center_x, mag_center_y))
                elif view.magnifier_visible_right:
                    slots[0] = make_slot((mag_center_x, mag_center_y), 1)
                    magnifier_centers.append((mag_center_x, mag_center_y))

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
            widget.zoom_level = render_scale
            widget.pan_offset_x = 0.5 - ((tile_left + (tile_w / 2.0)) / padded_w)
            widget.pan_offset_y = 0.5 - ((tile_top + (tile_h / 2.0)) / padded_h)
            widget.set_apply_channel_mode_in_shader(False)
            if diff_image is not None:
                widget.upload_diff_source_pil_image(diff_image)
            else:
                widget.upload_diff_source_pil_image(None)

            split_pos_local = int(
                round(
                    (view.split_position_visual * tile_h)
                    if view.is_horizontal
                    else (view.split_position_visual * tile_w)
                )
            )
            widget.set_split_line_params(
                render.divider_line_visible and diff_mode == "off",
                split_pos_local,
                view.is_horizontal,
                split_color,
                divider_thickness_export,
            )
            widget.set_guides_params(
                render.show_magnifier_guides,
                laser_color,
                guides_thickness_export,
            )
            widget.set_capture_color(capture_color)

            capture_center_local = None
            if render.show_capture_area_on_main_image:
                cap_local_x, cap_local_y = to_local_point(cap_center_x, cap_center_y)
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
            if view.use_magnifier:
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
            widget.makeCurrent()
            paint_gl(widget)
            widget.doneCurrent()
            QApplication.processEvents()
            tile_paint_total += (time.perf_counter() - paint_started) * 1000.0

            grab_started = time.perf_counter()
            tile_img = _qimage_to_pil(widget.grabFramebuffer())
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
            stroke_scales = _compute_export_stroke_scales(
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
            canvas_plan = _compute_canvas_plan(
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
            widget.makeCurrent()
            paint_gl(widget)
            widget.doneCurrent()
            QApplication.processEvents()
            debug_timings["paint_gl_ms"] = (
                time.perf_counter() - paint_started
            ) * 1000.0

            framebuffer_started = time.perf_counter()
            result_box["image"] = _qimage_to_pil(widget.grabFramebuffer())
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

class GpuExportService:
    def __init__(self, parent=None, resource_manager=None):
        self._proxy = _GpuExportProxy(parent, resource_manager=resource_manager)
        self._max_texture_size = None
        self._last_tiled_debug = {}

    def _request(self, payload: dict):
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
                raise ValueError("GPU render_image requires either render_context or explicit image arguments")
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
