from typing import Optional, Tuple

from PIL import Image
from PyQt6.QtCore import QPoint, QPointF

from domain.types import Point
from domain.qt_adapters import point_to_qpointf
from ui.canvas_features.magnifier import MagnifierStoreService
from ui.canvas_features.magnifier.state import get_magnifier_widget_state
from ui.canvas_features.magnifier.store import (
    default_capture_size,
    default_magnifier_size,
    magnifier_enabled,
    iter_magnifier_models,
)
from ui.canvas_infra.scene.widget_registry import get_canvas_feature_command
from .geometry import resolve_interpolation

def _build_divider_canvas_payload_from_store(store) -> dict:
    command = get_canvas_feature_command("divider", "render.canvas_payload")
    if command is None:
        return {"visible": False, "color": (255, 255, 255, 255), "thickness": 0}
    return command(store)

def _build_canvas_payload_from_store(store, feature_name: str, default: dict) -> dict:
    command = get_canvas_feature_command(feature_name, "render.canvas_payload")
    if command is None:
        return dict(default)
    return dict(command(store))

def _build_canvas_payload_from_params(params: dict, feature_name: str, default: dict) -> dict:
    payloads = params.get("canvas_feature_render_payloads", {}) or {}
    return dict(payloads.get(feature_name, default))

def _build_divider_canvas_payload_from_params(params: dict) -> dict:
    return _build_canvas_payload_from_params(
        params,
        "divider",
        {"visible": False, "color": (255, 255, 255, 255), "thickness": 0},
    )

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
    scene_state = MagnifierStoreService(store)
    magnifier_model = scene_state.get_active_or_first_magnifier()
    magnifier_state = get_magnifier_widget_state(view)
    divider_payload = _build_divider_canvas_payload_from_store(store)
    capture_payload = _build_canvas_payload_from_store(
        store,
        "capture",
        {"visible": True, "color": (255, 50, 100, 230)},
    )
    guides_payload = _build_canvas_payload_from_store(
        store,
        "guides",
        {
            "enabled": False,
            "thickness": 1,
            "color": (255, 255, 255, 255),
            "smoothing_enabled": False,
            "smoothing_interpolation_method": "BILINEAR",
        },
    )
    capture_areas = tuple(
        (
            float(model.position.x),
            float(model.position.y),
            float(model.capture_size_relative),
        )
        for model in iter_magnifier_models(view, render)
        if bool(model.visible) and bool(getattr(model, "show_capture_area", True))
    )

    optimize_laser = bool(guides_payload.get("smoothing_enabled", False))
    optimize_mag_mov = getattr(view, "optimize_magnifier_movement", True)
    main_interp = render.interpolation_method
    magnifier_movement_interp = getattr(
        render, "magnifier_movement_interpolation_method", "BILINEAR"
    )
    laser_smoothing_interp = str(guides_payload.get("smoothing_interpolation_method", "BILINEAR"))
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
    if magnifier_enabled(view) and magnifier_model is not None:
        ref_dim = min(width, height)
        visual_offset = (
            interaction.magnifier_offset_relative_visual
            if getattr(interaction, "is_interactive_mode", False)
            else magnifier_model.offset_relative
        )
        offset_x = int(visual_offset.x * ref_dim)
        offset_y = int(visual_offset.y * ref_dim)
        magnifier_offset = QPoint(offset_x, offset_y)

    return RenderContext(
        canvas=RenderCanvasContext(
            width=width,
            height=height,
            split_pos=view.split_position_visual,
            is_horizontal=view.is_horizontal,
            divider_line_visible=bool(divider_payload.get("visible", False)),
            divider_line_color=tuple(divider_payload.get("color", (255, 255, 255, 255))),
            divider_line_thickness=int(divider_payload.get("thickness", 0)),
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
            position=point_to_qpointf(magnifier_model.position if magnifier_model is not None else Point(0.5, 0.5)),
            offset=magnifier_offset,
            enabled=magnifier_enabled(view),
            size_relative=magnifier_model.size_relative if magnifier_model is not None else default_magnifier_size(view),
            capture_size_relative=magnifier_model.capture_size_relative if magnifier_model is not None else default_capture_size(view),
            show_capture_area=bool(capture_payload.get("visible", True)),
            capture_areas=capture_areas,
            drawing_coords=magnifier_drawing_coords,
            visible_left=bool(magnifier_model.visible_left) if magnifier_model is not None else True,
            visible_center=bool(magnifier_model.visible_center) if magnifier_model is not None else True,
            visible_right=bool(magnifier_model.visible_right) if magnifier_model is not None else True,
            combined=scene_state.is_active_magnifier_combined(),
            layout_horizontal=bool(magnifier_model.is_horizontal) if magnifier_model is not None else False,
            divider_visible=(
                bool(magnifier_model.divider_visible)
                if magnifier_model is not None
                else bool(magnifier_state.default_divider_visible)
            ),
            divider_color=(
                (magnifier_model.divider_color.r if magnifier_model is not None else magnifier_state.default_divider_color.r),
                (magnifier_model.divider_color.g if magnifier_model is not None else magnifier_state.default_divider_color.g),
                (magnifier_model.divider_color.b if magnifier_model is not None else magnifier_state.default_divider_color.b),
                (magnifier_model.divider_color.a if magnifier_model is not None else magnifier_state.default_divider_color.a),
            ),
            divider_thickness=(
                int(magnifier_model.divider_thickness)
                if magnifier_model is not None
                else int(magnifier_state.default_divider_thickness)
            ),
            internal_split=(
                interaction.magnifier_internal_split_visual
                if getattr(interaction, "is_interactive_mode", False)
                and magnifier_model is not None
                else (magnifier_model.internal_split if magnifier_model is not None else 0.5)
            ),
            border_color=(
                (magnifier_model.border_color.r if magnifier_model is not None else magnifier_state.default_border_color.r),
                (magnifier_model.border_color.g if magnifier_model is not None else magnifier_state.default_border_color.g),
                (magnifier_model.border_color.b if magnifier_model is not None else magnifier_state.default_border_color.b),
                (magnifier_model.border_color.a if magnifier_model is not None else magnifier_state.default_border_color.a),
            ),
            laser_color=tuple(guides_payload.get("color", (255, 255, 255, 255))),
            capture_ring_color=tuple(capture_payload.get("color", (255, 50, 100, 230))),
            show_guides=bool(guides_payload.get("enabled", False)),
            guides_thickness=int(guides_payload.get("thickness", 1)),
            interactive_mode=getattr(interaction, "is_interactive_mode", False),
            optimize_movement=optimize_mag_mov,
            optimize_laser_smoothing=optimize_laser,
            movement_interpolation_method=eff_mag_interp,
            laser_interpolation_method=eff_laser_interp,
            visual_offset_relative=(
                interaction.magnifier_offset_relative_visual
                if getattr(interaction, "is_interactive_mode", False)
                else magnifier_model.offset_relative
            )
            if magnifier_model is not None
            else None,
            visual_spacing_relative=(
                interaction.magnifier_spacing_relative_visual
                if getattr(interaction, "is_interactive_mode", False)
                else magnifier_model.spacing_relative
            )
            if magnifier_model is not None
            else 0.05,
            highlighted_element=getattr(view, "highlighted_magnifier_element", None),
            highlight_capture=bool(
                getattr(interaction, "is_dragging_capture_point", False)
            ),
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

    mag_pos_tuple = params.get("magnifier_position", (0.5, 0.5))
    capture_areas = tuple(
        (
            float(item[0]),
            float(item[1]),
            float(item[2]),
        )
        for item in params.get("magnifier_capture_areas", ())
        if len(item) >= 3
    )
    if isinstance(mag_pos_tuple, tuple) and len(mag_pos_tuple) >= 2:
        mag_pos = QPointF(float(mag_pos_tuple[0]), float(mag_pos_tuple[1]))
    elif isinstance(mag_pos_tuple, QPointF):
        mag_pos = QPointF(mag_pos_tuple)
    else:
        mag_pos = QPointF(0.5, 0.5)

    magnifier_offset = None
    if params.get("magnifier_enabled") and params.get("magnifier_visual_offset"):
        ref_dim = min(width, height)
        mag_offset_visual = params["magnifier_visual_offset"]
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
    if params.get("magnifier_visual_offset"):
        mag_offset_visual = params["magnifier_visual_offset"]
        if isinstance(mag_offset_visual, tuple):
            mag_offset_relative_visual_qpoint = QPointF(
                float(mag_offset_visual[0]), float(mag_offset_visual[1])
            )
        elif isinstance(mag_offset_visual, QPointF):
            mag_offset_relative_visual_qpoint = QPointF(mag_offset_visual)

    caches = session_caches or {}
    divider_payload = _build_divider_canvas_payload_from_params(params)
    capture_payload = _build_canvas_payload_from_params(
        params,
        "capture",
        {"visible": True, "color": (255, 50, 100, 230)},
    )
    guides_payload = _build_canvas_payload_from_params(
        params,
        "guides",
        {
            "enabled": False,
            "thickness": 1,
            "color": (255, 255, 255, 255),
            "smoothing_enabled": False,
            "smoothing_interpolation_method": "BILINEAR",
        },
    )
    return RenderContext(
        canvas=RenderCanvasContext(
            width=width,
            height=height,
            split_pos=params.get("split_pos", 0.5),
            is_horizontal=params.get("is_horizontal", False),
            divider_line_visible=bool(divider_payload.get("visible", False)),
            divider_line_color=tuple(divider_payload.get("color", (255, 255, 255, 255))),
            divider_line_thickness=int(divider_payload.get("thickness", 0)),
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
            position=mag_pos,
            offset=magnifier_offset,
            enabled=params.get("magnifier_enabled", False),
            size_relative=params.get("magnifier_size", 0.2),
            capture_size_relative=params.get("capture_size", 0.1),
            show_capture_area=bool(capture_payload.get("visible", params.get("show_capture_area", True))),
            capture_areas=capture_areas,
            drawing_coords=magnifier_drawing_coords,
            visible_left=params.get("magnifier_show_left", True),
            visible_center=params.get("magnifier_show_center", True),
            visible_right=params.get("magnifier_show_right", True),
            combined=params.get("magnifier_combined", False),
            layout_horizontal=params.get("magnifier_layout_horizontal", False),
            divider_visible=params.get("magnifier_divider_visible", True),
            divider_color=params.get("magnifier_divider_color", (255, 255, 255, 230)),
            divider_thickness=params.get("magnifier_divider_thickness", 2),
            internal_split=params.get("magnifier_split", 0.5),
            border_color=params.get("magnifier_border_color", (255, 255, 255, 248)),
            laser_color=tuple(guides_payload.get("color", params.get("magnifier_laser_color", (255, 255, 255, 255)))),
            capture_ring_color=tuple(capture_payload.get("color", params.get("capture_ring_color", (255, 50, 100, 230)))),
            show_guides=bool(guides_payload.get("enabled", params.get("magnifier_show_guides", False))),
            guides_thickness=int(guides_payload.get("thickness", params.get("magnifier_guides_thickness", 1))),
            interactive_mode=params.get("is_interactive_mode", False),
            optimize_movement=params.get("optimize_magnifier_movement", True),
            optimize_laser_smoothing=bool(guides_payload.get("smoothing_enabled", params.get("optimize_laser_smoothing", False))),
            movement_interpolation_method=params.get("movement_interpolation_method", "BILINEAR"),
            laser_interpolation_method=str(guides_payload.get("smoothing_interpolation_method", params.get("laser_smoothing_interpolation_method", "BILINEAR"))),
            visual_offset_relative=mag_offset_relative_visual_qpoint,
            visual_spacing_relative=params.get("magnifier_visual_spacing", 0.05),
            highlighted_element=params.get("highlighted_magnifier_element"),
            highlight_capture=bool(params.get("highlight_capture", False)),
            cache_dict=caches.get("magnifier_cache_dict"),
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
