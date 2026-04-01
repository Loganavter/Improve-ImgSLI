from typing import Optional, Tuple

from PIL import Image
from PyQt6.QtCore import QPoint, QPointF

from domain.qt_adapters import point_to_qpointf
from .geometry import resolve_interpolation

def create_render_context_from_store(
    store,
    width: int,
    height: int,
    magnifier_drawing_coords: Optional[Tuple] = None,
    image1_scaled: Optional[Image.Image] = None,
    image2_scaled: Optional[Image.Image] = None,
):
    from shared.image_processing.pipeline import RenderContext
    from shared.image_processing.pipeline import (
        RenderCanvasContext,
        RenderImageContext,
        RenderMagnifierContext,
        RenderModeContext,
        RenderTextContext,
    )

    viewport = store.viewport
    view = getattr(viewport, "view_state", viewport)
    render = getattr(viewport, "render_config", getattr(store, "settings", None))
    session = getattr(viewport, "session_data", viewport)
    interaction = getattr(viewport, "interaction_state", viewport)

    optimize_laser = getattr(render, "optimize_laser_smoothing", False)
    optimize_mag_mov = getattr(view, "optimize_magnifier_movement", True)
    main_interp = render.interpolation_method
    magnifier_movement_interp = getattr(
        render, "magnifier_movement_interpolation_method", "BILINEAR"
    )
    laser_smoothing_interp = getattr(
        render, "laser_smoothing_interpolation_method", "BILINEAR"
    )
    eff_mag_interp = (
        resolve_interpolation(main_interp, magnifier_movement_interp)
        if optimize_mag_mov
        else main_interp
    )
    eff_laser_interp = resolve_interpolation(main_interp, laser_smoothing_interp)

    img1 = (
        image1_scaled
        or session.image1
        or getattr(store.document, "original_image1", None)
        or Image.new("RGBA", (width, height))
    )
    img2 = (
        image2_scaled
        or session.image2
        or getattr(store.document, "original_image2", None)
        or Image.new("RGBA", (width, height))
    )

    name1, name2 = "", ""
    try:
        if 0 <= store.document.current_index1 < len(store.document.image_list1):
            name1 = store.document.image_list1[store.document.current_index1].display_name
        if 0 <= store.document.current_index2 < len(store.document.image_list2):
            name2 = store.document.image_list2[store.document.current_index2].display_name
    except Exception:
        pass

    magnifier_offset = None
    if view.use_magnifier:
        ref_dim = min(width, height)
        offset_x = int(view.magnifier_offset_relative_visual.x * ref_dim)
        offset_y = int(view.magnifier_offset_relative_visual.y * ref_dim)
        magnifier_offset = QPoint(offset_x, offset_y)

    return RenderContext(
        canvas=RenderCanvasContext(
            width=width,
            height=height,
            split_pos=view.split_position_visual,
            is_horizontal=view.is_horizontal,
            divider_line_visible=render.divider_line_visible,
            divider_line_color=(
                render.divider_line_color.r,
                render.divider_line_color.g,
                render.divider_line_color.b,
                render.divider_line_color.a,
            ),
            divider_line_thickness=render.divider_line_thickness,
            divider_clip_rect=getattr(view, "divider_clip_rect", None),
        ),
        images=RenderImageContext(
            image1=img1,
            image2=img2,
            original_image1=getattr(store.document, "original_image1", None)
            or getattr(store.document, "full_res_image1", None),
            original_image2=getattr(store.document, "original_image2", None)
            or getattr(store.document, "full_res_image2", None),
            file_name1=name1,
            file_name2=name2,
        ),
        mode=RenderModeContext(
            diff_mode=view.diff_mode,
            channel_view_mode=view.channel_view_mode,
            interpolation_method=render.interpolation_method,
        ),
        magnifier=RenderMagnifierContext(
            magnifier_pos=point_to_qpointf(view.capture_position_relative),
            magnifier_offset=magnifier_offset,
            use_magnifier=view.use_magnifier,
            magnifier_size=view.magnifier_size_relative,
            capture_size=view.capture_size_relative,
            show_capture_area=render.show_capture_area_on_main_image,
            magnifier_drawing_coords=magnifier_drawing_coords,
            magnifier_visible_left=view.magnifier_visible_left,
            magnifier_visible_center=view.magnifier_visible_center,
            magnifier_visible_right=view.magnifier_visible_right,
            is_magnifier_combined=view.is_magnifier_combined,
            magnifier_is_horizontal=view.magnifier_is_horizontal,
            magnifier_divider_visible=render.magnifier_divider_visible,
            magnifier_divider_color=(
                render.magnifier_divider_color.r,
                render.magnifier_divider_color.g,
                render.magnifier_divider_color.b,
                render.magnifier_divider_color.a,
            ),
            magnifier_divider_thickness=render.magnifier_divider_thickness,
            magnifier_internal_split=view.magnifier_internal_split,
            magnifier_border_color=(
                render.magnifier_border_color.r,
                render.magnifier_border_color.g,
                render.magnifier_border_color.b,
                render.magnifier_border_color.a,
            ),
            magnifier_laser_color=(
                render.magnifier_laser_color.r,
                render.magnifier_laser_color.g,
                render.magnifier_laser_color.b,
                render.magnifier_laser_color.a,
            ),
            capture_ring_color=(
                render.capture_ring_color.r,
                render.capture_ring_color.g,
                render.capture_ring_color.b,
                render.capture_ring_color.a,
            ),
            show_magnifier_guides=render.show_magnifier_guides,
            magnifier_guides_thickness=render.magnifier_guides_thickness,
            is_interactive_mode=getattr(interaction, "is_interactive_mode", False),
            optimize_magnifier_movement=optimize_mag_mov,
            optimize_laser_smoothing=optimize_laser,
            movement_interpolation_method=eff_mag_interp,
            magnifier_movement_interpolation_method=eff_mag_interp,
            laser_smoothing_interpolation_method=eff_laser_interp,
            magnifier_offset_relative_visual=view.magnifier_offset_relative_visual,
            magnifier_spacing_relative_visual=view.magnifier_spacing_relative_visual,
            highlighted_magnifier_element=getattr(view, "highlighted_magnifier_element", None),
        ),
        text=RenderTextContext(
            include_file_names=render.include_file_names_in_saved,
            font_size_percent=render.font_size_percent,
            font_weight=render.font_weight,
            text_alpha_percent=render.text_alpha_percent,
            file_name_color=(
                render.file_name_color.r,
                render.file_name_color.g,
                render.file_name_color.b,
                render.file_name_color.a,
            ),
            file_name_bg_color=(
                render.file_name_bg_color.r,
                render.file_name_bg_color.g,
                render.file_name_bg_color.b,
                render.file_name_bg_color.a,
            ),
            draw_text_background=render.draw_text_background,
            text_placement_mode=render.text_placement_mode,
            max_name_length=render.max_name_length,
        ),
    )

def create_render_context_from_params(
    render_params_dict: dict,
    width: int,
    height: int,
    magnifier_drawing_coords: Optional[Tuple] = None,
    image1_scaled: Optional[Image.Image] = None,
    image2_scaled: Optional[Image.Image] = None,
    original_image1: Optional[Image.Image] = None,
    original_image2: Optional[Image.Image] = None,
    file_name1: str = "",
    file_name2: str = "",
    session_caches: dict = None,
):
    from shared.image_processing.pipeline import RenderContext
    from shared.image_processing.pipeline import (
        RenderCanvasContext,
        RenderImageContext,
        RenderMagnifierContext,
        RenderModeContext,
        RenderTextContext,
    )

    params = render_params_dict
    img1 = image1_scaled or original_image1 or Image.new("RGBA", (width, height), (0, 0, 0, 255))
    img2 = image2_scaled or original_image2 or Image.new("RGBA", (width, height), (0, 0, 0, 255))

    mag_pos_tuple = params.get("magnifier_pos", (0.5, 0.5))
    if isinstance(mag_pos_tuple, tuple) and len(mag_pos_tuple) >= 2:
        mag_pos = QPointF(float(mag_pos_tuple[0]), float(mag_pos_tuple[1]))
    elif isinstance(mag_pos_tuple, QPointF):
        mag_pos = QPointF(mag_pos_tuple)
    else:
        mag_pos = QPointF(0.5, 0.5)

    magnifier_offset = None
    if params.get("use_magnifier") and params.get("magnifier_offset_relative_visual"):
        ref_dim = min(width, height)
        mag_offset_visual = params["magnifier_offset_relative_visual"]
        if isinstance(mag_offset_visual, tuple):
            offset_x = int(mag_offset_visual[0] * ref_dim)
            offset_y = int(mag_offset_visual[1] * ref_dim)
        elif isinstance(mag_offset_visual, QPointF):
            offset_x = int(mag_offset_visual.x() * ref_dim)
            offset_y = int(mag_offset_visual.y() * ref_dim)
        else:
            offset_x = offset_y = 0
        magnifier_offset = QPoint(offset_x, offset_y)

    mag_offset_relative_visual_qpoint = None
    if params.get("magnifier_offset_relative_visual"):
        mag_offset_visual = params["magnifier_offset_relative_visual"]
        if isinstance(mag_offset_visual, tuple):
            mag_offset_relative_visual_qpoint = QPointF(
                float(mag_offset_visual[0]), float(mag_offset_visual[1])
            )
        elif isinstance(mag_offset_visual, QPointF):
            mag_offset_relative_visual_qpoint = QPointF(mag_offset_visual)

    caches = session_caches or {}
    return RenderContext(
        canvas=RenderCanvasContext(
            width=width,
            height=height,
            split_pos=params.get("split_pos", 0.5),
            is_horizontal=params.get("is_horizontal", False),
            divider_line_visible=params.get("divider_line_visible", True),
            divider_line_color=params.get("divider_line_color", (255, 255, 255, 255)),
            divider_line_thickness=params.get("divider_line_thickness", 3),
            divider_clip_rect=params.get("divider_clip_rect"),
        ),
        images=RenderImageContext(
            image1=img1,
            image2=img2,
            original_image1=original_image1,
            original_image2=original_image2,
            file_name1=file_name1,
            file_name2=file_name2,
            background_cache_dict=caches.get("background_cache_dict"),
        ),
        mode=RenderModeContext(
            diff_mode=params.get("diff_mode", "off"),
            channel_view_mode=params.get("channel_view_mode", "RGB"),
            interpolation_method=params.get("interpolation_method", "BILINEAR"),
        ),
        magnifier=RenderMagnifierContext(
            magnifier_pos=mag_pos,
            magnifier_offset=magnifier_offset,
            use_magnifier=params.get("use_magnifier", False),
            magnifier_size=params.get("magnifier_size", 0.2),
            capture_size=params.get("capture_size", 0.1),
            show_capture_area=params.get("show_capture_area", True),
            magnifier_drawing_coords=magnifier_drawing_coords,
            magnifier_visible_left=params.get("magnifier_visible_left", True),
            magnifier_visible_center=params.get("magnifier_visible_center", True),
            magnifier_visible_right=params.get("magnifier_visible_right", True),
            is_magnifier_combined=params.get("is_magnifier_combined", False),
            magnifier_is_horizontal=params.get("magnifier_is_horizontal", False),
            magnifier_divider_visible=params.get("magnifier_divider_visible", True),
            magnifier_divider_color=params.get("magnifier_divider_color", (255, 255, 255, 230)),
            magnifier_divider_thickness=params.get("magnifier_divider_thickness", 2),
            magnifier_internal_split=params.get("magnifier_internal_split", 0.5),
            magnifier_border_color=params.get("magnifier_border_color", (255, 255, 255, 248)),
            magnifier_laser_color=params.get("magnifier_laser_color", (255, 255, 255, 255)),
            capture_ring_color=params.get("capture_ring_color", (255, 50, 100, 230)),
            show_magnifier_guides=params.get("show_magnifier_guides", False),
            magnifier_guides_thickness=params.get("magnifier_guides_thickness", 1),
            is_interactive_mode=params.get("is_interactive_mode", False),
            optimize_magnifier_movement=params.get("optimize_magnifier_movement", True),
            optimize_laser_smoothing=params.get("optimize_laser_smoothing", False),
            movement_interpolation_method=params.get("movement_interpolation_method", "BILINEAR"),
            magnifier_movement_interpolation_method=params.get("magnifier_movement_interpolation_method", "BILINEAR"),
            laser_smoothing_interpolation_method=params.get("laser_smoothing_interpolation_method", "BILINEAR"),
            magnifier_offset_relative_visual=mag_offset_relative_visual_qpoint,
            magnifier_spacing_relative_visual=params.get("magnifier_spacing_relative_visual", 0.05),
            highlighted_magnifier_element=params.get("highlighted_magnifier_element"),
            magnifier_cache_dict=caches.get("magnifier_cache_dict"),
        ),
        text=RenderTextContext(
            include_file_names=params.get("include_file_names", False),
            font_size_percent=params.get("font_size_percent", 100),
            font_weight=params.get("font_weight", 0),
            text_alpha_percent=params.get("text_alpha_percent", 100),
            file_name_color=params.get("file_name_color", (255, 0, 0, 255)),
            file_name_bg_color=params.get("file_name_bg_color", (0, 0, 0, 80)),
            draw_text_background=params.get("draw_text_background", True),
            text_placement_mode=params.get("text_placement_mode", "edges"),
            max_name_length=params.get("max_name_length", 50),
        ),
    )
