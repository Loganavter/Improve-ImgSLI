from __future__ import annotations

from dataclasses import dataclass, field

from PyQt6.QtGui import QColor

@dataclass(frozen=True)
class GLFilenameOverlayConfig:
    enabled: bool = False
    image_display_rect: tuple[int, int, int, int] | None = None
    text_placement_mode: str = "edges"
    split_position: float = 0.5
    is_horizontal: bool = False
    divider_thickness: int = 0
    is_interactive_mode: bool = False
    draw_text_background: bool = True
    font_size_percent: int = 100
    font_weight: int = 0
    text_alpha_percent: int = 100
    file_name_color: object | None = None
    file_name_bg_color: object | None = None
    name1: str = ""
    name2: str = ""

@dataclass(frozen=True)
class GLRenderScene:
    blank_white: bool = False
    single_image_preview: bool = False
    clip_overlays_to_image_bounds: bool = False
    is_horizontal: bool = False
    split_position_visual: float = 0.5
    divider_clip_rect: tuple[int, int, int, int] | None = None
    show_divider: bool = False
    divider_color: QColor = field(
        default_factory=lambda: QColor(255, 255, 255, 255)
    )
    divider_thickness: int = 2
    render_magnifiers: bool = True
    border_color: QColor = field(
        default_factory=lambda: QColor(255, 255, 255, 248)
    )
    capture_color: QColor = field(
        default_factory=lambda: QColor(255, 50, 100, 230)
    )
    laser_color: QColor = field(
        default_factory=lambda: QColor(255, 255, 255, 120)
    )
    show_guides: bool = False
    guides_thickness: int = 1
    interactive_mode: bool = False
    optimize_laser_smoothing: bool = False
    channel_mode_int: int = 0
    diff_mode_active: bool = False
    zoom_interpolation_method: str = "BILINEAR"
    filename_overlay: GLFilenameOverlayConfig = field(
        default_factory=GLFilenameOverlayConfig
    )

def build_gl_render_scene(
    store,
    *,
    apply_channel_mode_in_shader: bool,
    clip_overlays_to_image_bounds: bool = False,
) -> GLRenderScene:
    if store is None:
        return GLRenderScene()

    from domain.qt_adapters import color_to_qcolor

    viewport = getattr(store, "viewport", None)
    document = getattr(store, "document", None)
    if viewport is None:
        return GLRenderScene()

    diff_mode = str(getattr(viewport.view_state, "diff_mode", "off") or "off")
    is_horizontal = bool(getattr(viewport.view_state, "is_horizontal", False))
    split_position_visual = float(getattr(viewport.view_state, "split_position_visual", 0.5))
    divider_clip_rect = getattr(viewport, "divider_clip_rect", None)
    zoom_method = str(
        getattr(getattr(viewport, "render_config", None), "zoom_interpolation_method", "BILINEAR")
        or "BILINEAR"
    )

    image_display_rect = getattr(viewport.geometry_state, "image_display_rect_on_label", None)
    if image_display_rect is not None:
        image_display_rect = (
            int(getattr(image_display_rect, "x", 0)),
            int(getattr(image_display_rect, "y", 0)),
            int(getattr(image_display_rect, "w", 0)),
            int(getattr(image_display_rect, "h", 0)),
        )

    filename_overlay = GLFilenameOverlayConfig(
        enabled=bool(getattr(viewport.render_config, "include_file_names_in_saved", False)),
        image_display_rect=image_display_rect,
        text_placement_mode=str(getattr(viewport.render_config, "text_placement_mode", "edges")),
        split_position=split_position_visual,
        is_horizontal=is_horizontal,
        divider_thickness=int(getattr(viewport.render_config, "divider_line_thickness", 0)),
        is_interactive_mode=bool(getattr(viewport.interaction_state, "is_interactive_mode", False)),
        draw_text_background=bool(getattr(viewport.render_config, "draw_text_background", True)),
        font_size_percent=int(getattr(viewport.render_config, "font_size_percent", 100)),
        font_weight=int(getattr(viewport.render_config, "font_weight", 0)),
        text_alpha_percent=int(getattr(viewport.render_config, "text_alpha_percent", 100)),
        file_name_color=getattr(viewport.render_config, "file_name_color", None),
        file_name_bg_color=getattr(viewport.render_config, "file_name_bg_color", None),
        name1=document.get_current_display_name(1) if document is not None else "",
        name2=document.get_current_display_name(2) if document is not None else "",
    )

    return GLRenderScene(
        blank_white=not bool(
            document is not None
            and getattr(document, "image1_path", None)
            and getattr(document, "image2_path", None)
        ),
        single_image_preview=bool(getattr(viewport.view_state, "showing_single_image_mode", 0) != 0),
        clip_overlays_to_image_bounds=bool(clip_overlays_to_image_bounds),
        is_horizontal=is_horizontal,
        split_position_visual=split_position_visual,
        divider_clip_rect=divider_clip_rect,
        show_divider=bool(
            getattr(viewport.render_config, "divider_line_visible", False)
            and diff_mode == "off"
            and getattr(viewport.view_state, "showing_single_image_mode", 0) == 0
        ),
        divider_color=color_to_qcolor(getattr(viewport.render_config, "divider_line_color", None)),
        divider_thickness=int(getattr(viewport.render_config, "divider_line_thickness", 2)),
        render_magnifiers=bool(getattr(viewport.view_state, "use_magnifier", False)),
        border_color=color_to_qcolor(getattr(viewport.render_config, "magnifier_border_color", None)),
        capture_color=color_to_qcolor(getattr(viewport.render_config, "capture_ring_color", None)),
        laser_color=color_to_qcolor(getattr(viewport.render_config, "magnifier_laser_color", None)),
        show_guides=bool(getattr(viewport.render_config, "show_capture_area_on_main_image", False)),
        guides_thickness=int(getattr(viewport, "magnifier_laser_thickness", 1)),
        interactive_mode=bool(getattr(viewport.interaction_state, "is_interactive_mode", False)),
        optimize_laser_smoothing=bool(getattr(viewport.render_config, "optimize_laser_smoothing", False)),
        channel_mode_int=(
            {"RGB": 0, "R": 1, "G": 2, "B": 3, "L": 4}.get(
                str(getattr(viewport.view_state, "channel_view_mode", "RGB") or "RGB"),
                0,
            )
            if apply_channel_mode_in_shader
            else 0
        ),
        diff_mode_active=diff_mode != "off",
        zoom_interpolation_method=zoom_method,
        filename_overlay=filename_overlay,
    )
