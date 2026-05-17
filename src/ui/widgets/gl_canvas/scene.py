from __future__ import annotations

from dataclasses import dataclass, field

from PyQt6.QtGui import QColor

from ui.canvas_infra.scene.widget_registry import build_canvas_feature_render_scene_overrides

@dataclass(frozen=True)
class GLRenderScene:
    blank_white: bool = False
    single_image_preview: int = 0
    clip_overlays_to_image_bounds: bool = False
    is_horizontal: bool = False
    split_position_visual: float = 0.5
    divider_clip_rect: tuple[int, int, int, int] | None = None
    show_divider: bool = False
    divider_color: QColor = field(
        default_factory=lambda: QColor(255, 255, 255, 255)
    )
    divider_thickness: int = 2
    channel_mode_int: int = 0
    diff_mode_active: bool = False
    diff_mode_int: int = 0
    zoom_interpolation_method: str = "BILINEAR"
    feature_overrides: dict = field(default_factory=dict)

def build_gl_render_scene(
    store,
    *,
    apply_channel_mode_in_shader: bool,
    clip_overlays_to_image_bounds: bool = False,
) -> GLRenderScene:
    if store is None:
        return GLRenderScene()

    viewport = getattr(store, "viewport", None)
    if viewport is None:
        return GLRenderScene()

    diff_mode = str(getattr(viewport.view_state, "diff_mode", "off") or "off")
    is_horizontal = bool(getattr(viewport.view_state, "is_horizontal", False))
    split_position_visual = float(getattr(viewport.view_state, "split_position_visual", 0.5))
    divider_clip_rect = getattr(viewport, "overlay_clip_rect", None)
    zoom_method = str(
        getattr(getattr(viewport, "render_config", None), "zoom_interpolation_method", "BILINEAR")
        or "BILINEAR"
    )
    feature_overrides = build_canvas_feature_render_scene_overrides(store)

    diff_mode_int = {"off": 0, "highlight": 1, "grayscale": 2, "edges": 3, "ssim": 4}.get(
        diff_mode, 0,
    )

    document = getattr(store, "document", None)
    is_single_preview = int(getattr(viewport.view_state, "showing_single_image_mode", 0) or 0)

    return GLRenderScene(
        blank_white=not bool(
            document is not None
            and getattr(document, "image1_path", None)
            and getattr(document, "image2_path", None)
        ),
        single_image_preview=is_single_preview,
        clip_overlays_to_image_bounds=bool(clip_overlays_to_image_bounds),
        is_horizontal=is_horizontal,
        split_position_visual=split_position_visual,
        divider_clip_rect=divider_clip_rect,
        show_divider=bool(feature_overrides.get("show_divider", False)),
        divider_color=feature_overrides.get("divider_color", QColor(255, 255, 255, 255)),
        divider_thickness=int(feature_overrides.get("divider_thickness", 2)),
        channel_mode_int=(
            {"RGB": 0, "R": 1, "G": 2, "B": 3, "L": 4}.get(
                str(getattr(viewport.view_state, "channel_view_mode", "RGB") or "RGB"),
                0,
            )
            if apply_channel_mode_in_shader
            else 0
        ),
        diff_mode_active=diff_mode != "off" and not is_single_preview,
        diff_mode_int=0 if is_single_preview else diff_mode_int,
        zoom_interpolation_method=zoom_method,
        feature_overrides=feature_overrides,
    )
