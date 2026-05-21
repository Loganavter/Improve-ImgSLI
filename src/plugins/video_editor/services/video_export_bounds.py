from __future__ import annotations

import logging
from core.store import Store
from shared.rendering import NormalizedBounds, resolve_virtual_canvas_layout
from plugins.video_editor.services.video_export_models import GlobalCanvasBounds
from ui.canvas_infra.scene.widget_registry import get_canvas_feature_commands_by_id

_blog = logging.getLogger("ImproveImgSLI.bounds_analyzer")

class CanvasBoundsAnalyzer:
    def __init__(self, image_loader) -> None:
        self._image_loader = image_loader

    def calculate(self, snapshots, auto_crop: bool = False) -> GlobalCanvasBounds | None:
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
            img1 = self._image_loader(snap.image1_path, auto_crop)
            if img1:
                w, h = img1.size
                base_w = max(base_w, w)
                base_h = max(base_h, h)

            img2 = self._image_loader(snap.image2_path, auto_crop)
            if img2:
                w, h = img2.size
                base_w = max(base_w, w)
                base_h = max(base_h, h)

        if base_w == 0 or base_h == 0:
            return None

        build_requirements = get_canvas_feature_commands_by_id(
            "render.layout_requirement"
        )
        _blog.info(
            "BOUNDS base=%sx%s layout_requirement_commands=%s snapshots=%s",
            base_w, base_h, len(build_requirements) if build_requirements else 0,
            len(snapshots),
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
            img1 = self._image_loader(snap.image1_path, auto_crop)
            img2 = self._image_loader(snap.image2_path, auto_crop)
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

            requirements = []
            for build_requirement in build_requirements:
                requirement = build_requirement(
                    temp_store,
                    drawing_width=base_w,
                    drawing_height=base_h,
                )
                if requirement is not None:
                    requirements.append(requirement)
            if requirements:
                layout = resolve_virtual_canvas_layout(requirements)
                pad_left, pad_right, pad_top, pad_bottom = layout.resolve_padding_pixels(
                    base_width=base_w,
                    base_height=base_h,
                )
                resolved_canvas_bounds = layout.canvas_bounds
            else:
                pad_left, pad_right, pad_top, pad_bottom = (0, 0, 0, 0)
                resolved_canvas_bounds = None
            _blog.info(
                "BOUNDS_SNAP img1=%s img2=%s requirements=%s "
                "pad=(%s,%s,%s,%s) canvas_bounds=%s",
                snap.image1_path, snap.image2_path,
                len(requirements),
                pad_left, pad_right, pad_top, pad_bottom,
                resolved_canvas_bounds,
            )
            max_pad_left = max(max_pad_left, pad_left)
            max_pad_right = max(max_pad_right, pad_right)
            max_pad_top = max(max_pad_top, pad_top)
            max_pad_bottom = max(max_pad_bottom, pad_bottom)
            if resolved_canvas_bounds is not None:
                canvas_bounds = canvas_bounds.union(resolved_canvas_bounds)
                have_explicit_layout = True

        final_canvas_bounds = canvas_bounds if have_explicit_layout else NormalizedBounds.unit()
        _blog.info(
            "BOUNDS_FINAL base=%sx%s max_pad=(%s,%s,%s,%s) "
            "canvas_bounds=(%.4f,%.4f,%.4f,%.4f) explicit=%s",
            base_w, base_h,
            max_pad_left, max_pad_right, max_pad_top, max_pad_bottom,
            final_canvas_bounds.x_min, final_canvas_bounds.x_max,
            final_canvas_bounds.y_min, final_canvas_bounds.y_max,
            have_explicit_layout,
        )
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
