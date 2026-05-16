from __future__ import annotations

from dataclasses import replace

from PIL import Image
from PyQt6.QtGui import QColor, QImage

from ui.canvas_infra.scene.widget_registry import get_canvas_feature_command_by_alias
from ui.widgets.gl_canvas.scene import build_gl_render_scene

def build_export_gl_scene(store, divider_thickness_export: int):
    scene = build_gl_render_scene(
        store,
        apply_channel_mode_in_shader=True,
        clip_overlays_to_image_bounds=False,
    )
    old_overlay = scene.feature_overrides.get("filename_overlay")
    new_feature_overrides = {
        **scene.feature_overrides,
        **(
            {"filename_overlay": replace(old_overlay, divider_thickness=divider_thickness_export)}
            if old_overlay is not None
            else {}
        ),
    }
    return replace(
        scene,
        divider_thickness=divider_thickness_export,
        feature_overrides=new_feature_overrides,
    )

def adjust_scene_for_padded_canvas(
    scene,
    *,
    pad_left: int,
    pad_top: int,
    image_w: int,
    image_h: int,
    canvas_w: int,
    canvas_h: int,
):
    if pad_left == 0 and pad_top == 0:
        return scene
    raw_split = scene.split_position_visual
    if scene.is_horizontal and canvas_h > 0 and image_h > 0:
        adjusted = (pad_top + raw_split * image_h) / canvas_h
    elif not scene.is_horizontal and canvas_w > 0 and image_w > 0:
        adjusted = (pad_left + raw_split * image_w) / canvas_w
    else:
        return scene
    return replace(scene, split_position_visual=adjusted)

def adjust_scene_split_for_tile(
    scene,
    *,
    pad_left: int,
    pad_top: int,
    image_w: int,
    image_h: int,
    tile_left: int,
    tile_top: int,
    tile_w: int,
    tile_h: int,
):
    raw_split = scene.split_position_visual
    if scene.is_horizontal and tile_h > 0 and image_h > 0:
        adjusted = (pad_top + raw_split * image_h - tile_top) / tile_h
    elif not scene.is_horizontal and tile_w > 0 and image_w > 0:
        adjusted = (pad_left + raw_split * image_w - tile_left) / tile_w
    else:
        return scene
    return replace(scene, split_position_visual=adjusted)

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
    return command(
        store,
        scale_x=scale_x,
        scale_y=scale_y,
        content_offset_x=content_offset_x,
        content_offset_y=content_offset_y,
        content_width=content_width,
        content_height=content_height,
    )

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

def qimage_to_pil(image: QImage) -> Image.Image:
    qimg = image.convertToFormat(QImage.Format.Format_RGBA8888)
    ptr = qimg.bits()
    ptr.setsize(qimg.sizeInBytes())
    return Image.frombytes("RGBA", (qimg.width(), qimg.height()), bytes(ptr))
