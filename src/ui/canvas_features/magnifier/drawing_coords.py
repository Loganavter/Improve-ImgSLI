from __future__ import annotations

import logging
import math

from PyQt6.QtCore import QPoint, QPointF, QRect

from core.store import Store

from .store import MagnifierStoreService

_mlog = logging.getLogger("ImproveImgSLI.video_magnifier_layout")

MIN_CAPTURE_THICKNESS = 2.0

def get_magnifier_drawing_coords(
    store: Store,
    drawing_width: int,
    drawing_height: int,
    container_width: int | None = None,
    container_height: int | None = None,
) -> tuple[
    tuple[float, float, float, float] | None,
    tuple[float, float, float, float] | None,
    QPoint | None,
    int,
    int,
    QRect,
    QPointF | None,
]:
    empty_result = (None, None, None, 0, 0, QRect(), None)

    full_res_img1 = store.document.full_res_image1 or store.document.original_image1
    full_res_img2 = store.document.full_res_image2 or store.document.original_image2

    if not full_res_img1 or not full_res_img2:
        return empty_result

    unified_width, unified_height = drawing_width, drawing_height
    full1_width, full1_height = full_res_img1.size
    full2_width, full2_height = full_res_img2.size

    if not all(
        [
            unified_width > 0,
            unified_height > 0,
            full1_width > 0,
            full1_height > 0,
            full2_width > 0,
            full2_height > 0,
        ]
    ):
        return empty_result

    scene_state = MagnifierStoreService(store)
    magnifier = scene_state.get_active_or_first_magnifier()
    if magnifier is None:
        return empty_result

    unified_ref_dim = math.sqrt(float(unified_width) * float(unified_height))
    capture_size_on_unified = float(magnifier.capture_size_relative) * unified_ref_dim

    drawing_ref_dim = max(1, min(drawing_width, drawing_height))
    thickness_on_unified = max(
        int(MIN_CAPTURE_THICKNESS),
        int(round(drawing_ref_dim * 0.003)),
    )

    inner_capture_size_on_unified = capture_size_on_unified - thickness_on_unified
    if inner_capture_size_on_unified <= 0:
        inner_capture_size_on_unified = (
            max(1, int(round(capture_size_on_unified - thickness_on_unified))) or 1
        )

    radius_rel_x = (
        (capture_size_on_unified / 2.0) / unified_width if unified_width > 0 else 0.0
    )
    radius_rel_y = (
        (capture_size_on_unified / 2.0) / unified_height if unified_height > 0 else 0.0
    )

    interaction = getattr(store.viewport, "interaction_state", None)
    use_visual_motion = bool(
        interaction
        and getattr(interaction, "is_interactive_mode", False)
        and getattr(store.viewport.view_state, "optimize_interactive_movement", True)
    )

    raw_pos = magnifier.position

    eff_rel_x = max(radius_rel_x, min(raw_pos.x, 1.0 - radius_rel_x))
    eff_rel_y = max(radius_rel_y, min(raw_pos.y, 1.0 - radius_rel_y))

    capture_center_full1_x = eff_rel_x * full1_width
    capture_center_full1_y = eff_rel_y * full1_height
    capture_center_full2_x = eff_rel_x * full2_width
    capture_center_full2_y = eff_rel_y * full2_height

    capture_frac_w = inner_capture_size_on_unified / unified_width
    capture_frac_h = inner_capture_size_on_unified / unified_height

    crop_width1 = int(round(capture_frac_w * full1_width))
    crop_height1 = int(round(capture_frac_h * full1_height))
    crop_width2 = int(round(capture_frac_w * full2_width))
    crop_height2 = int(round(capture_frac_h * full2_height))

    if crop_width1 % 2 != 0:
        crop_width1 += 1
    if crop_height1 % 2 != 0:
        crop_height1 += 1
    if crop_width2 % 2 != 0:
        crop_width2 += 1
    if crop_height2 % 2 != 0:
        crop_height2 += 1

    left1 = int(round(capture_center_full1_x - crop_width1 / 2.0))
    top1 = int(round(capture_center_full1_y - crop_height1 / 2.0))
    left2 = int(round(capture_center_full2_x - crop_width2 / 2.0))
    top2 = int(round(capture_center_full2_y - crop_height2 / 2.0))

    crop_box1 = (left1, top1, left1 + crop_width1, top1 + crop_height1)
    crop_box2 = (left2, top2, left2 + crop_width2, top2 + crop_height2)

    magnifier_midpoint_on_image = QPoint()
    magnifier_bbox_on_image = QRect()
    magnifier_size_pixels = 0
    edge_spacing_pixels = 0

    if bool(magnifier.visible):
        target_max_dim_drawing = math.sqrt(float(drawing_width) * float(drawing_height))
        magnifier_size_pixels = max(10, int(round(magnifier.size_relative * target_max_dim_drawing)))

        spacing_visual = (
            float(
                getattr(
                    interaction,
                    "interactive_spacing_relative_visual",
                    magnifier.spacing_relative,
                )
            )
            if use_visual_motion
            else float(magnifier.spacing_relative)
        )
        edge_spacing_pixels = max(
            0,
            int(round(spacing_visual * target_max_dim_drawing)),
        )

        if magnifier.freeze and magnifier.frozen_position:
            base_pos_x = magnifier.frozen_position.x
            base_pos_y = magnifier.frozen_position.y
        else:
            base_pos_x = eff_rel_x
            base_pos_y = eff_rel_y

        offset_visual = (
            getattr(interaction, "interactive_offset_relative_visual", magnifier.offset_relative)
            if use_visual_motion
            else magnifier.offset_relative
        )

        mid_x = int(
            round(
                base_pos_x * drawing_width
                + offset_visual.x * target_max_dim_drawing
            )
        )
        mid_y = int(
            round(
                base_pos_y * drawing_height
                + offset_visual.y * target_max_dim_drawing
            )
        )
        magnifier_midpoint_on_image = QPoint(mid_x, mid_y)

        r = magnifier_size_pixels // 2

        rect_center = QRect(
            int(round(mid_x - r)),
            int(round(mid_y - r)),
            int(round(magnifier_size_pixels)),
            int(round(magnifier_size_pixels)),
        )
        magnifier_bbox_on_image = rect_center

        is_visual_diff = store.viewport.view_state.diff_mode in (
            "highlight",
            "grayscale",
            "ssim",
            "edges",
        )

        if is_visual_diff:
            show_left = bool(magnifier.visible_left)
            show_right = bool(magnifier.visible_right)

            if scene_state.is_active_magnifier_combined():
                shift = magnifier_size_pixels + 8
                if not magnifier.is_horizontal:
                    rect_combined = QRect(
                        int(round(mid_x - r)),
                        int(round(mid_y + shift - r)),
                        int(round(magnifier_size_pixels)),
                        int(round(magnifier_size_pixels)),
                    )
                else:
                    rect_combined = QRect(
                        int(round(mid_x + shift - r)),
                        int(round(mid_y - r)),
                        int(round(magnifier_size_pixels)),
                        int(round(magnifier_size_pixels)),
                    )

                magnifier_bbox_on_image = rect_center.united(rect_combined)

            else:
                spacing_f = float(edge_spacing_pixels)
                offset_dist = max(
                    magnifier_size_pixels, magnifier_size_pixels + spacing_f
                )

                if not magnifier.is_horizontal:
                    center_left = QPoint(int(round(mid_x - offset_dist)), mid_y)
                    center_right = QPoint(int(round(mid_x + offset_dist)), mid_y)
                else:
                    center_left = QPoint(mid_x, int(round(mid_y - offset_dist)))
                    center_right = QPoint(mid_x, int(round(mid_y + offset_dist)))

                rect_left = QRect(
                    int(round(center_left.x() - r)),
                    int(round(center_left.y() - r)),
                    int(round(magnifier_size_pixels)),
                    int(round(magnifier_size_pixels)),
                )
                rect_right = QRect(
                    int(round(center_right.x() - r)),
                    int(round(center_right.y() - r)),
                    int(round(magnifier_size_pixels)),
                    int(round(magnifier_size_pixels)),
                )

                if show_left:
                    magnifier_bbox_on_image = magnifier_bbox_on_image.united(rect_left)
                if show_right:
                    magnifier_bbox_on_image = magnifier_bbox_on_image.united(rect_right)

        else:
            if scene_state.is_active_magnifier_combined():
                magnifier_bbox_on_image = rect_center
            else:
                dist = r + int(round(edge_spacing_pixels / 2.0))

                if not magnifier.is_horizontal:
                    rect1 = QRect(
                        int(round(mid_x - dist - r)),
                        int(round(mid_y - r)),
                        int(round(magnifier_size_pixels)),
                        int(round(magnifier_size_pixels)),
                    )
                    rect2 = QRect(
                        int(round(mid_x + dist - r)),
                        int(round(mid_y - r)),
                        int(round(magnifier_size_pixels)),
                        int(round(magnifier_size_pixels)),
                    )
                else:
                    rect1 = QRect(
                        int(round(mid_x - r)),
                        int(round(mid_y - dist - r)),
                        int(round(magnifier_size_pixels)),
                        int(round(magnifier_size_pixels)),
                    )
                    rect2 = QRect(
                        int(round(mid_x - r)),
                        int(round(mid_y + dist - r)),
                        int(round(magnifier_size_pixels)),
                        int(round(magnifier_size_pixels)),
                    )

                magnifier_bbox_on_image = rect1.united(rect2)

    capture_center_on_image = QPointF(
        eff_rel_x * unified_width, eff_rel_y * unified_height
    )

    out_of_bounds = (
        left1 < 0
        or top1 < 0
        or left2 < 0
        or top2 < 0
        or crop_box1[2] > full1_width
        or crop_box1[3] > full1_height
        or crop_box2[2] > full2_width
        or crop_box2[3] > full2_height
        or magnifier_bbox_on_image.left() < 0
        or magnifier_bbox_on_image.top() < 0
        or magnifier_bbox_on_image.right() > drawing_width
        or magnifier_bbox_on_image.bottom() > drawing_height
    )
    if out_of_bounds:
        _mlog.debug(
            "magnifier_drawing_coords drawing=%sx%s full1=%sx%s full2=%sx%s raw_pos=(%.6f,%.6f) eff_pos=(%.6f,%.6f) capture_size=%.6f crop1=%s crop2=%s mag_mid=(%s,%s) mag_size=%s spacing=%s bbox=(%s,%s,%s,%s) capture_center=(%.3f,%.3f)",
            drawing_width,
            drawing_height,
            full1_width,
            full1_height,
            full2_width,
            full2_height,
            float(raw_pos.x),
            float(raw_pos.y),
            float(eff_rel_x),
            float(eff_rel_y),
            float(magnifier.capture_size_relative),
            crop_box1,
            crop_box2,
            magnifier_midpoint_on_image.x(),
            magnifier_midpoint_on_image.y(),
            magnifier_size_pixels,
            edge_spacing_pixels,
            magnifier_bbox_on_image.x(),
            magnifier_bbox_on_image.y(),
            magnifier_bbox_on_image.width(),
            magnifier_bbox_on_image.height(),
            float(capture_center_on_image.x()),
            float(capture_center_on_image.y()),
        )

    return (
        crop_box1,
        crop_box2,
        magnifier_midpoint_on_image,
        magnifier_size_pixels,
        edge_spacing_pixels,
        magnifier_bbox_on_image,
        capture_center_on_image,
    )
