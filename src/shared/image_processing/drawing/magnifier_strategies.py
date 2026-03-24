from PIL import Image

from .magnifier_diff import build_optional_diff_patch
from .magnifier_layout import (
    compute_diff_combined_position,
    compute_three_magnifier_side_centers,
    compute_two_magnifier_centers,
    set_magnifier_combined_mode,
)

def draw_visible_side_magnifiers(
    drawer,
    *,
    image_to_draw_on: Image.Image,
    center_left,
    center_right,
    crop_box1: tuple,
    crop_box2: tuple,
    magnifier_size: int,
    image1_for_crop: Image.Image,
    image2_for_crop: Image.Image,
    interpolation_method: str,
    is_interactive: bool,
    show_left: bool,
    show_right: bool,
    border_color: tuple,
):
    if show_left:
        drawer._draw_single_visible_magnifier(
            image_to_draw_on=image_to_draw_on,
            display_center_pos=center_left,
            crop_box_orig=crop_box1,
            magnifier_size=magnifier_size,
            image_for_crop=image1_for_crop,
            interpolation_method=interpolation_method,
            is_interactive=is_interactive,
            border_color=border_color,
        )
    if show_right:
        drawer._draw_single_visible_magnifier(
            image_to_draw_on=image_to_draw_on,
            display_center_pos=center_right,
            crop_box_orig=crop_box2,
            magnifier_size=magnifier_size,
            image_for_crop=image2_for_crop,
            interpolation_method=interpolation_method,
            is_interactive=is_interactive,
            border_color=border_color,
        )

def draw_diff_combined_bottom_magnifier(
    drawer,
    *,
    image_to_draw_on: Image.Image,
    image1_for_crop: Image.Image,
    image2_for_crop: Image.Image,
    crop_box1: tuple,
    crop_box2: tuple,
    midpoint,
    magnifier_size: int,
    interpolation_method: str,
    is_interactive: bool,
    comb_is_horizontal: bool,
    comb_split: float,
    comb_divider_visible: bool,
    comb_divider_color: tuple,
    comb_divider_thickness: int,
    layout_horizontal: bool,
    border_color: tuple,
):
    combined_pos = compute_diff_combined_position(
        midpoint=midpoint,
        magnifier_size=magnifier_size,
        layout_horizontal=layout_horizontal,
    )
    drawer.draw_combined_magnifier_circle(
        target_image=image_to_draw_on,
        display_center_pos=combined_pos,
        crop_box1=crop_box1,
        crop_box2=crop_box2,
        magnifier_size_pixels=magnifier_size,
        image1_for_crop=image1_for_crop,
        image2_for_crop=image2_for_crop,
        interpolation_method=interpolation_method,
        is_horizontal=comb_is_horizontal,
        is_interactive_render=is_interactive,
        internal_split=comb_split,
        divider_visible=comb_divider_visible,
        divider_color=comb_divider_color,
        divider_thickness=comb_divider_thickness,
        border_color=border_color,
    )
    return combined_pos

def draw_strategy_three_magnifiers(drawer, **kwargs):
    try:
        set_magnifier_combined_mode(kwargs["store"], combined=False)
        center_left, center_right = compute_three_magnifier_side_centers(
            midpoint=kwargs["midpoint"],
            magnifier_size=kwargs["magnifier_size"],
            spacing=kwargs["spacing"],
            layout_horizontal=kwargs["layout_horizontal"],
        )
        draw_visible_side_magnifiers(
            drawer,
            image_to_draw_on=kwargs["image_to_draw_on"],
            center_left=center_left,
            center_right=center_right,
            crop_box1=kwargs["crop_box1"],
            crop_box2=kwargs["crop_box2"],
            magnifier_size=kwargs["magnifier_size"],
            image1_for_crop=kwargs["image1_for_crop"],
            image2_for_crop=kwargs["image2_for_crop"],
            interpolation_method=kwargs["interpolation_method"],
            is_interactive=kwargs["is_interactive"],
            show_left=kwargs["show_left"],
            show_right=kwargs["show_right"],
            border_color=kwargs["border_color"],
        )
        drawer._draw_center_diff_magnifier(
            image_to_draw_on=kwargs["image_to_draw_on"],
            midpoint=kwargs["midpoint"],
            magnifier_size=kwargs["magnifier_size"],
            diff_center_patch=build_optional_diff_patch(
                drawer,
                show_center=kwargs["show_center"],
                store=kwargs["store"],
                diff_mode=kwargs["diff_mode"],
                magnifier_size=kwargs["magnifier_size"],
                image1_for_crop=kwargs["image1_for_crop"],
                image2_for_crop=kwargs["image2_for_crop"],
                crop_box1=kwargs["crop_box1"],
                crop_box2=kwargs["crop_box2"],
                interpolation_method=kwargs["interpolation_method"],
                is_interactive=kwargs["is_interactive"],
                font_path=kwargs["font_path"],
            ),
            interpolation_method=kwargs["interpolation_method"],
            border_color=kwargs["border_color"],
        )
    except Exception:
        pass

def draw_strategy_diff_top_combined_bottom(drawer, **kwargs):
    combined_pos_result = None
    try:
        diff_patch = build_optional_diff_patch(
            drawer,
            show_center=kwargs["show_center"],
            store=kwargs["store"],
            diff_mode=kwargs["diff_mode"],
            magnifier_size=kwargs["magnifier_size"],
            image1_for_crop=kwargs["image1_for_crop"],
            image2_for_crop=kwargs["image2_for_crop"],
            crop_box1=kwargs["crop_box1"],
            crop_box2=kwargs["crop_box2"],
            interpolation_method=kwargs["interpolation_method"],
            is_interactive=kwargs["is_interactive"],
            font_path=kwargs["font_path"],
        )
        drawer._draw_center_diff_magnifier(
            image_to_draw_on=kwargs["image_to_draw_on"],
            midpoint=kwargs["midpoint"],
            magnifier_size=kwargs["magnifier_size"],
            diff_center_patch=diff_patch,
            interpolation_method=kwargs["interpolation_method"],
            border_color=kwargs["border_color"],
        )
        if kwargs["show_left"] and kwargs["show_right"]:
            combined_pos_result = draw_diff_combined_bottom_magnifier(
                drawer,
                image_to_draw_on=kwargs["image_to_draw_on"],
                image1_for_crop=kwargs["image1_for_crop"],
                image2_for_crop=kwargs["image2_for_crop"],
                crop_box1=kwargs["crop_box1"],
                crop_box2=kwargs["crop_box2"],
                midpoint=kwargs["midpoint"],
                magnifier_size=kwargs["magnifier_size"],
                interpolation_method=kwargs["interpolation_method"],
                is_interactive=kwargs["is_interactive"],
                comb_is_horizontal=kwargs["comb_is_horizontal"],
                comb_split=kwargs["comb_split"],
                comb_divider_visible=kwargs["comb_divider_visible"],
                comb_divider_color=kwargs["comb_divider_color"],
                comb_divider_thickness=kwargs["comb_divider_thickness"],
                layout_horizontal=kwargs["layout_horizontal"],
                border_color=kwargs["border_color"],
            )
    except Exception:
        pass
    return combined_pos_result

def draw_strategy_two_magnifiers(drawer, **kwargs):
    try:
        set_magnifier_combined_mode(kwargs["store"], combined=False)
        if not (kwargs["show_left"] or kwargs["show_right"]):
            return
        if kwargs["show_left"] and kwargs["show_right"]:
            center1, center2 = compute_two_magnifier_centers(
                midpoint=kwargs["midpoint"],
                magnifier_size=kwargs["magnifier_size"],
                spacing=kwargs["spacing"],
                layout_horizontal=kwargs["layout_horizontal"],
            )
            draw_visible_side_magnifiers(
                drawer,
                image_to_draw_on=kwargs["image_to_draw_on"],
                center_left=center1,
                center_right=center2,
                crop_box1=kwargs["crop_box1"],
                crop_box2=kwargs["crop_box2"],
                magnifier_size=kwargs["magnifier_size"],
                image1_for_crop=kwargs["image1_for_crop"],
                image2_for_crop=kwargs["image2_for_crop"],
                interpolation_method=kwargs["interpolation_method"],
                is_interactive=kwargs["is_interactive"],
                show_left=True,
                show_right=True,
                border_color=kwargs["border_color"],
            )
        elif kwargs["show_left"]:
            drawer._draw_single_visible_magnifier(
                image_to_draw_on=kwargs["image_to_draw_on"],
                display_center_pos=kwargs["midpoint"],
                crop_box_orig=kwargs["crop_box1"],
                magnifier_size=kwargs["magnifier_size"],
                image_for_crop=kwargs["image1_for_crop"],
                interpolation_method=kwargs["interpolation_method"],
                is_interactive=kwargs["is_interactive"],
                border_color=kwargs["border_color"],
            )
        else:
            drawer._draw_single_visible_magnifier(
                image_to_draw_on=kwargs["image_to_draw_on"],
                display_center_pos=kwargs["midpoint"],
                crop_box_orig=kwargs["crop_box2"],
                magnifier_size=kwargs["magnifier_size"],
                image_for_crop=kwargs["image2_for_crop"],
                interpolation_method=kwargs["interpolation_method"],
                is_interactive=kwargs["is_interactive"],
                border_color=kwargs["border_color"],
            )
    except Exception:
        pass

def draw_strategy_combined_single(drawer, **kwargs):
    try:
        drawer.draw_combined_magnifier_circle(
            target_image=kwargs["image_to_draw_on"],
            display_center_pos=kwargs["midpoint"],
            crop_box1=kwargs["crop_box1"],
            crop_box2=kwargs["crop_box2"],
            magnifier_size_pixels=kwargs["magnifier_size"],
            image1_for_crop=kwargs["image1_for_crop"],
            image2_for_crop=kwargs["image2_for_crop"],
            interpolation_method=kwargs["interpolation_method"],
            is_horizontal=kwargs["is_horizontal"],
            is_interactive_render=kwargs["is_interactive"],
            internal_split=kwargs["internal_split"],
            divider_visible=kwargs["divider_visible"],
            divider_color=kwargs["divider_color"],
            divider_thickness=kwargs["divider_thickness"],
            border_color=kwargs["border_color"],
            external_cache=kwargs["external_cache"],
        )
    except Exception:
        pass
