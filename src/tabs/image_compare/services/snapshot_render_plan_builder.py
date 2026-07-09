from __future__ import annotations

import logging
from dataclasses import replace

from PIL import Image
from PySide6.QtGui import QColor

_pblog = logging.getLogger("ImproveImgSLI.plan_builder")

from core.store import Store
from shared.analysis import build_cached_diff_image
from plugins.export.services.gpu_export_layout import compute_export_stroke_scales
from tabs.image_compare.services.gpu_export_scene import (
    build_export_gl_scene,
)
from plugins.video_editor.services.video_export_models import GlobalCanvasBounds
from shared.rendering import (
    NormalizedBounds,
    TargetSurfaceSpec,
)
from tabs.image_compare.canvas.presentation.plan_builder import (
    build_canvas_plan,
    compute_canvas_plan,
)
from ui.canvas_infra.scene.layout_requirements import resolve_feature_virtual_layout
from ui.canvas_infra.scene.widget_registry import (
    get_canvas_feature_command_by_alias,
    get_canvas_feature_commands_by_id,
)


def build_divider_export_overlay(
    store,
    *,
    scale_x: float,
    scale_y: float,
    content_offset_x: float,
    content_offset_y: float,
    content_width: float,
    content_height: float,
) -> dict:
    command = get_canvas_feature_command_by_alias("splitter.export_overlay")
    if command is None:
        return {
            "visible": False,
            "split_pos": 0,
            "is_horizontal": False,
            "color": QColor(),
            "thickness": 0,
        }
    result = command(
        store,
        scale_x=scale_x,
        scale_y=scale_y,
        content_offset_x=content_offset_x,
        content_offset_y=content_offset_y,
        content_width=content_width,
        content_height=content_height,
    )
    return result


def query_guides_state(view):
    command = get_canvas_feature_command_by_alias("guides.widget_state")
    if command is not None:
        return command(view)
    return type(
        "_FallbackGuidesState",
        (),
        {
            "enabled": False,
            "thickness": 1,
            "color": type("C", (), {"r": 255, "g": 255, "b": 255, "a": 255})(),
        },
    )()


def query_active_magnifier_divider_thickness(store) -> int:
    command = get_canvas_feature_command_by_alias("overlay.active_divider_thickness")
    return int(command(store) if command is not None else 0)


def calculate_still_snapshot_bounds(snap, image1, image2) -> GlobalCanvasBounds:
    base_w = max(
        1,
        int(getattr(image1, "width", 0) or 0),
        int(getattr(image2, "width", 0) or 0),
    )
    base_h = max(
        1,
        int(getattr(image1, "height", 0) or 0),
        int(getattr(image2, "height", 0) or 0),
    )

    temp_store = Store()
    temp_store.viewport = snap.viewport_state.clone()
    temp_store.settings = snap.settings_state.freeze_for_export()
    temp_store.viewport.session_data.image_state.image1 = image1
    temp_store.viewport.session_data.image_state.image2 = image2
    temp_store.document.full_res_image1 = image1
    temp_store.document.full_res_image2 = image2
    temp_store.viewport.geometry_state.pixmap_width = base_w
    temp_store.viewport.geometry_state.pixmap_height = base_h

    layout = resolve_feature_virtual_layout(
        temp_store, drawing_width=base_w, drawing_height=base_h
    )
    if layout is not None:
        pad_left, pad_right, pad_top, pad_bottom = layout.resolve_padding_pixels(
            base_width=base_w,
            base_height=base_h,
        )
        canvas_bounds = layout.canvas_bounds
    else:
        pad_left, pad_right, pad_top, pad_bottom = (0, 0, 0, 0)
        canvas_bounds = NormalizedBounds.unit()

    return GlobalCanvasBounds(
        pad_left=pad_left,
        pad_right=pad_right,
        pad_top=pad_top,
        pad_bottom=pad_bottom,
        base_width=base_w,
        base_height=base_h,
        canvas_x_min=float(canvas_bounds.x_min),
        canvas_x_max=float(canvas_bounds.x_max),
        canvas_y_min=float(canvas_bounds.y_min),
        canvas_y_max=float(canvas_bounds.y_max),
    )


def calculate_global_canvas_bounds(
    snapshots,
    image_loader,
    auto_crop: bool = False,
) -> GlobalCanvasBounds | None:
    if not snapshots:
        return None

    max_pad_left = 0
    max_pad_right = 0
    max_pad_top = 0
    max_pad_bottom = 0
    base_w, base_h = 0, 0
    canvas_bounds = NormalizedBounds.unit()
    have_explicit_layout = False

    for snap in snapshots:
        img1 = image_loader(snap.image1_path, auto_crop)
        if img1:
            w, h = img1.size
            base_w = max(base_w, w)
            base_h = max(base_h, h)

        img2 = image_loader(snap.image2_path, auto_crop)
        if img2:
            w, h = img2.size
            base_w = max(base_w, w)
            base_h = max(base_h, h)

    if base_w == 0 or base_h == 0:
        return None

    build_requirements = get_canvas_feature_commands_by_id(
        "render.layout_requirement"
    )
    if not build_requirements:
        return GlobalCanvasBounds(
            pad_left=0,
            pad_right=0,
            pad_top=0,
            pad_bottom=0,
            base_width=base_w,
            base_height=base_h,
        )

    for snap in snapshots:
        img1 = image_loader(snap.image1_path, auto_crop)
        img2 = image_loader(snap.image2_path, auto_crop)
        if not img1 or not img2:
            continue

        temp_store = Store()
        temp_store.viewport = snap.viewport_state.clone()
        temp_store.settings = snap.settings_state.freeze_for_export()
        temp_store.viewport.session_data.image_state.image1 = img1
        temp_store.viewport.session_data.image_state.image2 = img2
        temp_store.document.full_res_image1 = img1
        temp_store.document.full_res_image2 = img2
        temp_store.viewport.geometry_state.pixmap_width = base_w
        temp_store.viewport.geometry_state.pixmap_height = base_h

        layout = resolve_feature_virtual_layout(
            temp_store, drawing_width=base_w, drawing_height=base_h
        )
        if layout is not None and layout.canvas_bounds != layout.content_bounds:
            pad_left, pad_right, pad_top, pad_bottom = layout.resolve_padding_pixels(
                base_width=base_w,
                base_height=base_h,
            )
            resolved_canvas_bounds = layout.canvas_bounds
        else:
            pad_left, pad_right, pad_top, pad_bottom = (0, 0, 0, 0)
            resolved_canvas_bounds = None
        max_pad_left = max(max_pad_left, pad_left)
        max_pad_right = max(max_pad_right, pad_right)
        max_pad_top = max(max_pad_top, pad_top)
        max_pad_bottom = max(max_pad_bottom, pad_bottom)
        if resolved_canvas_bounds is not None:
            canvas_bounds = canvas_bounds.union(resolved_canvas_bounds)
            have_explicit_layout = True

    final_canvas_bounds = canvas_bounds if have_explicit_layout else NormalizedBounds.unit()
    return GlobalCanvasBounds(
        pad_left=max_pad_left,
        pad_right=max_pad_right,
        pad_top=max_pad_top,
        pad_bottom=max_pad_bottom,
        base_width=base_w,
        base_height=base_h,
        canvas_x_min=float(final_canvas_bounds.x_min),
        canvas_x_max=float(final_canvas_bounds.x_max),
        canvas_y_min=float(final_canvas_bounds.y_min),
        canvas_y_max=float(final_canvas_bounds.y_max),
    )


class SnapshotRenderPlanBuilder:
    def __init__(self, store) -> None:
        self.store = store

    @staticmethod
    def _is_featureless_canvas_geometry(canvas_geometry) -> bool:
        if canvas_geometry is None:
            return True
        return (
            getattr(canvas_geometry, "virtual_layout", None) is None
            and int(getattr(canvas_geometry, "padding_left", 0) or 0) == 0
            and int(getattr(canvas_geometry, "padding_right", 0) or 0) == 0
            and int(getattr(canvas_geometry, "padding_top", 0) or 0) == 0
            and int(getattr(canvas_geometry, "padding_bottom", 0) or 0) == 0
            and int(getattr(canvas_geometry, "canvas_width", 0) or 0)
            == int(getattr(canvas_geometry, "image_width", 0) or 0)
            and int(getattr(canvas_geometry, "canvas_height", 0) or 0)
            == int(getattr(canvas_geometry, "image_height", 0) or 0)
        )

    def build_render_plan(
        self,
        image1,
        image2,
        *,
        source_image1=None,
        source_image2=None,
        source_key=None,
        display_cache_key=None,
        target_surface: TargetSurfaceSpec | None = None,
        canvas_fill_rgba=None,
        canvas_geometry=None,
        allow_feature_layout_fallback: bool = False,
        scene_images_cache: dict | None = None,
    ):
        if target_surface is not None and canvas_fill_rgba is None:
            canvas_fill_rgba = target_surface.fill_rgba
        if source_image1 is None:
            source_image1 = image1
        if source_image2 is None:
            source_image2 = image2

        diff_mode = str(
            getattr(self.store.viewport.view_state, "diff_mode", "off") or "off"
        )
        channel_mode = str(
            getattr(self.store.viewport.view_state, "channel_view_mode", "RGB") or "RGB"
        )

        computed_canvas_plan = compute_canvas_plan(
            self.store,
            image1.width,
            image1.height,
        )
        canvas_plan = (
            computed_canvas_plan
            if allow_feature_layout_fallback
            and self._is_featureless_canvas_geometry(canvas_geometry)
            else canvas_geometry
        )
        if canvas_plan is None:
            canvas_plan = (
                computed_canvas_plan
                if allow_feature_layout_fallback
                else compute_canvas_plan(
                    self.store,
                    image1.width,
                    image1.height,
                )
            )

        scene_cache_key = (
            id(image1),
            id(image2),
            id(source_image1),
            id(source_image2),
            canvas_plan.canvas_width,
            canvas_plan.canvas_height,
            canvas_plan.padding_left,
            canvas_plan.padding_top,
            diff_mode,
            channel_mode,
            canvas_fill_rgba,
        )
        if (
            scene_images_cache is not None
            and scene_images_cache.get("key") == scene_cache_key
        ):
            scene_images = scene_images_cache["value"]
            cached_diff_image = scene_images.get("raw_diff")
        else:
            cached_diff_image = None
            if diff_mode in {"highlight", "grayscale", "edges", "ssim"}:
                cached_diff_image = build_cached_diff_image(
                    image1,
                    image2,
                    diff_mode,
                    channel_mode,
                )
            scene_images = self._prepare_canvas_scene_images(
                canvas_plan=canvas_plan,
                image1=image1,
                image2=image2,
                source_image1=source_image1,
                source_image2=source_image2,
                cached_diff_image=cached_diff_image,
                canvas_fill_rgba=canvas_fill_rgba,
            )
            if scene_images_cache is not None:
                scene_images_cache["key"] = scene_cache_key
                scene_images_cache["value"] = scene_images
        try:
            self.store.viewport.session_data.render_cache.cached_diff_image = (
                cached_diff_image
            )
        except Exception:
            pass

        viewport_state = {
            "pixmap_width": getattr(
                self.store.viewport.geometry_state, "pixmap_width", 0
            ),
            "pixmap_height": getattr(
                self.store.viewport.geometry_state, "pixmap_height", 0
            ),
        }
        scale_x, scale_y, _scale_ref = compute_export_stroke_scales(
            viewport_state,
            image1.width,
            image1.height,
        )
        vp = self.store.viewport
        view = vp.view_state
        guides_state = query_guides_state(view)
        divider_overlay = build_divider_export_overlay(
            self.store,
            scale_x=scale_x,
            scale_y=scale_y,
            content_offset_x=canvas_plan.padding_left,
            content_offset_y=canvas_plan.padding_top,
            content_width=canvas_plan.image_width,
            content_height=canvas_plan.image_height,
        )
        divider_thickness_export = int(divider_overlay.get("thickness", 0))
        guides_thickness_export = int(guides_state.thickness)
        magnifier_divider_thickness_export = query_active_magnifier_divider_thickness(
            self.store
        )
        gl_scene = build_export_gl_scene(
            self.store,
            divider_thickness_export,
            virtual_layout=canvas_plan.virtual_layout,
            image_w=canvas_plan.image_width,
            image_h=canvas_plan.image_height,
        )
        base_image1 = scene_images["bg1"]
        base_image2 = scene_images["bg2"]
        if scene_images["diff"] is not None:
            base_image1 = scene_images["diff"]
            base_image2 = scene_images["diff"]
            display_cache_key = (
                "diff_base",
                display_cache_key,
                diff_mode,
                channel_mode,
                scene_cache_key,
            )
            gl_scene = replace(
                gl_scene,
                diff_mode_active=False,
                diff_mode_int=0,
                channel_mode_int=0,
            )

        plan = build_canvas_plan(
            self.store,
            base_image1,
            base_image2,
            source_image1=scene_images["src1"],
            source_image2=scene_images["src2"],
            source_key=source_key or (),
            display_cache_key=display_cache_key,
            target_size=(canvas_plan.canvas_width, canvas_plan.canvas_height),
            content_size=(canvas_plan.image_width, canvas_plan.image_height),
            pad_left=canvas_plan.padding_left,
            pad_top=canvas_plan.padding_top,
            gl_scene=gl_scene,
            divider_thickness_px=magnifier_divider_thickness_export,
            guides_thickness=guides_thickness_export,
            output_scale=(
                float(target_surface.output_scale)
                if target_surface is not None
                else 1.0
            ),
            fill_color=canvas_fill_rgba,
            preserve_zoom=(
                bool(target_surface.preserve_zoom)
                if target_surface is not None
                else False
            ),
            image_is_padded_composite=True,
        )
        return plan

    @staticmethod
    def _pad_scene_image(
        image: Image.Image | None,
        *,
        canvas_w: int,
        canvas_h: int,
        pad_left: int,
        pad_top: int,
        fill_rgba: tuple[int, int, int, int],
    ):
        if image is None:
            return None
        result = Image.new("RGBA", (canvas_w, canvas_h), fill_rgba)
        result.paste(image.convert("RGBA"), (pad_left, pad_top))
        return result

    def _prepare_canvas_scene_images(
        self,
        *,
        canvas_plan,
        image1,
        image2,
        source_image1,
        source_image2,
        cached_diff_image,
        canvas_fill_rgba=None,
    ):
        aligned_source1 = source_image1
        aligned_source2 = source_image2
        export_size = (
            getattr(image1, "size", None),
            getattr(image2, "size", None),
        )
        source_size = (
            getattr(aligned_source1, "size", None),
            getattr(aligned_source2, "size", None),
        )
        if source_size != export_size:
            aligned_source1 = image1
            aligned_source2 = image2

        fill_rgba = tuple(canvas_fill_rgba or (0, 0, 0, 0))
        canvas_w = int(canvas_plan.canvas_width)
        canvas_h = int(canvas_plan.canvas_height)
        pad_left = int(canvas_plan.padding_left)
        pad_top = int(canvas_plan.padding_top)
        scene_images = {
            "bg1": self._pad_scene_image(
                image1,
                canvas_w=canvas_w,
                canvas_h=canvas_h,
                pad_left=pad_left,
                pad_top=pad_top,
                fill_rgba=fill_rgba,
            ),
            "bg2": self._pad_scene_image(
                image2,
                canvas_w=canvas_w,
                canvas_h=canvas_h,
                pad_left=pad_left,
                pad_top=pad_top,
                fill_rgba=fill_rgba,
            ),
            "src1": aligned_source1,
            "src2": aligned_source2,
            "diff": self._pad_scene_image(
                cached_diff_image,
                canvas_w=canvas_w,
                canvas_h=canvas_h,
                pad_left=pad_left,
                pad_top=pad_top,
                fill_rgba=fill_rgba,
            )
            if cached_diff_image is not None
            else None,
            "raw_diff": cached_diff_image,
        }
        return scene_images
