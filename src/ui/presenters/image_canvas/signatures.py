from ui.canvas_infra.scene.property_access import (
    read_canvas_feature_color_by_setting_key,
    read_canvas_feature_property,
)
from ui.canvas_infra.scene.widget_registry import (
    get_canvas_feature_command_by_alias,
    get_canvas_feature_properties,
)

class _FallbackGuidesState:
    enabled = False
    thickness = 1
    color = None
    smoothing_enabled = False
    smoothing_interpolation_method = "BILINEAR"

def _get_guides_state(view_state):
    query = get_canvas_feature_command_by_alias("guides.widget_state")
    if query is not None:
        return query(view_state)
    return _FallbackGuidesState()

def _get_effective_main_interpolation_method(vp):
    viewport_value = getattr(vp.render_config, "interpolation_method", None)
    if viewport_value:
        return viewport_value
    render_cfg = getattr(vp, "render_config", None)
    return getattr(render_cfg, "interpolation_method", "BILINEAR") if render_cfg else "BILINEAR"

def _get_effective_magnifier_interpolation_method(vp, *, is_interactive: bool):
    render = vp.render_config
    if is_interactive:
        return str(
            getattr(render, "interactive_movement_interpolation_method", "BILINEAR")
            or "BILINEAR"
        )
    return _get_effective_main_interpolation_method(vp)

def _query_overlay(store, capability_id: str, default=None):
    command = get_canvas_feature_command_by_alias(capability_id)
    if command is None:
        return default
    result = command(store)
    return default if result is None else result

def _query_overlay_from_viewport(vp, capability_id: str, default=None):
    store = type("StoreProxy", (), {"viewport": vp})()
    return _query_overlay(store, capability_id, default)

def _magnifier_models_signature(magnifier_models):
    signature = []
    for model in magnifier_models:
        signature.append(
            (
                model["id"],
                bool(model["visible"]),
                model["position"],
                float(model["size_relative"]),
                float(model["capture_size_relative"]),
                model["offset_relative"],
                float(model["spacing_relative"]),
                float(model["internal_split"]),
                bool(model["is_horizontal"]),
                bool(model["visible_left"]),
                bool(model["visible_center"]),
                bool(model["visible_right"]),
                bool(model["freeze"]),
                model["frozen_position"],
                model["border_color"],
            )
        )
    return tuple(signature)

def _canvas_feature_properties_signature(viewport):
    signature = []
    for prop in get_canvas_feature_properties():
        channels = read_canvas_feature_property(viewport, prop)
        signature.append((prop.id, tuple(sorted(channels.items()))))
    return tuple(signature)

def get_render_params_signature(presenter, s1, s2):
    vp = presenter.store.viewport
    view = vp.view_state
    render = vp.render_config
    doc = presenter.store.document
    capture_color = read_canvas_feature_color_by_setting_key(vp, "capture.color")
    guides_state = _get_guides_state(view)
    magnifier = _query_overlay(presenter.store, "overlay.active_state")
    magnifier_models = tuple(_query_overlay(presenter.store, "overlay.all_states", ()) or ())
    magnifier_models_sig = _magnifier_models_signature(magnifier_models)
    feature_props_sig = _canvas_feature_properties_signature(vp)
    magnifier_enabled = bool(_query_overlay(presenter.store, "overlay.enabled", False))
    divider_thickness = int(
        _query_overlay(presenter.store, "overlay.active_divider_thickness", 0) or 0
    )
    divider_color = _query_overlay(presenter.store, "overlay.active_divider_color")
    divider_visible = bool(
        _query_overlay(presenter.store, "overlay.active_divider_visible", False)
    )
    border_color = _query_overlay(presenter.store, "overlay.active_border_color")
    combined = bool(_query_overlay(presenter.store, "overlay.active_combined", False))
    if magnifier is None:
        return (
            None,
            feature_props_sig,
            magnifier_models_sig,
            view.split_position_visual,
            magnifier_enabled,
            guides_state.enabled,
            guides_state.thickness,
            None,
            None,
            False,
            None,
            None,
            view.diff_mode,
            view.channel_view_mode,
            view.is_horizontal,
            None,
            None,
            None,
            divider_thickness,
            divider_color,
            divider_visible,
            border_color,
            guides_state.color,
            capture_color,
            None,
            None,
            render.include_file_names_in_saved,
            render.font_size_percent,
            render.font_weight,
            render.text_alpha_percent,
            render.file_name_color,
            render.file_name_bg_color,
            render.draw_text_background,
            render.text_placement_mode,
            render.max_name_length,
            getattr(render, "movement_interpolation_method", None),
            render.interactive_movement_interpolation_method,
            guides_state.smoothing_interpolation_method,
            view.optimize_interactive_movement,
            guides_state.smoothing_enabled,
            doc.get_current_display_name(1),
            doc.get_current_display_name(2),
            id(s1),
            id(s2),
        )
    return (
        magnifier["position"],
        feature_props_sig,
        magnifier_models_sig,
        magnifier["visible"],
        view.split_position_visual,
        magnifier_enabled,
        guides_state.enabled,
        guides_state.thickness,
        magnifier["capture_size_relative"],
        magnifier["size_relative"],
        combined,
        magnifier["internal_split"],
        magnifier["is_horizontal"],
        view.diff_mode,
        view.channel_view_mode,
        view.is_horizontal,
        magnifier["visible_left"],
        magnifier["visible_center"],
        magnifier["visible_right"],
        divider_thickness,
        divider_color,
        divider_visible,
        border_color,
        guides_state.color,
        capture_color,
        magnifier["offset_relative"],
        magnifier["spacing_relative"],
        render.include_file_names_in_saved,
        render.font_size_percent,
        render.font_weight,
        render.text_alpha_percent,
        render.file_name_color,
        render.file_name_bg_color,
        render.draw_text_background,
        render.text_placement_mode,
        render.max_name_length,
        getattr(render, "movement_interpolation_method", None),
        render.interactive_movement_interpolation_method,
        guides_state.smoothing_interpolation_method,
        view.optimize_interactive_movement,
        guides_state.smoothing_enabled,
        doc.get_current_display_name(1),
        doc.get_current_display_name(2),
        id(s1),
        id(s2),
    )

def get_background_signature(presenter, s1, s2):
    vp = presenter.store.viewport
    view = vp.view_state
    render = vp.render_config
    geometry = vp.geometry_state
    doc = presenter.store.document
    feature_props_sig = _canvas_feature_properties_signature(vp)
    return (
        id(s1),
        id(s2),
        feature_props_sig,
        geometry.pixmap_width,
        geometry.pixmap_height,
        view.split_position_visual,
        view.is_horizontal,
        view.diff_mode,
        view.channel_view_mode,
        render.include_file_names_in_saved,
        doc.get_current_display_name(1),
        doc.get_current_display_name(2),
        render.font_size_percent,
        render.font_weight,
        render.text_alpha_percent,
        render.file_name_color,
        render.file_name_bg_color,
        render.draw_text_background,
        render.text_placement_mode,
        render.max_name_length,
    )

def get_magnifier_signature(presenter):
    vp = presenter.store.viewport
    view = vp.view_state
    render = vp.render_config
    capture_color = read_canvas_feature_color_by_setting_key(vp, "capture.color")
    guides_state = _get_guides_state(view)
    magnifier = _query_overlay(presenter.store, "overlay.active_state")
    magnifier_models_sig = _magnifier_models_signature(
        tuple(_query_overlay(presenter.store, "overlay.all_states", ()) or ())
    )
    magnifier_enabled = bool(_query_overlay(presenter.store, "overlay.enabled", False))
    combined = bool(_query_overlay(presenter.store, "overlay.active_combined", False))
    border_color = _query_overlay(presenter.store, "overlay.active_border_color")
    divider_visible = bool(
        _query_overlay(presenter.store, "overlay.active_divider_visible", False)
    )
    divider_color = _query_overlay(presenter.store, "overlay.active_divider_color")
    divider_thickness = int(
        _query_overlay(presenter.store, "overlay.active_divider_thickness", 0) or 0
    )
    if magnifier is None:
        return (magnifier_enabled, magnifier_models_sig, None, None)
    interaction = vp.interaction_state
    is_interactive = interaction.is_interactive_mode
    interp_method = _get_effective_magnifier_interpolation_method(
        vp,
        is_interactive=is_interactive,
    )

    if is_interactive:
        offset_for_sig = interaction.interactive_offset_relative_visual
        spacing_for_sig = interaction.interactive_spacing_relative_visual
        internal_split_for_sig = interaction.interactive_internal_split_visual
    else:
        offset_for_sig = magnifier["offset_relative"]
        spacing_for_sig = magnifier["spacing_relative"]
        internal_split_for_sig = magnifier["internal_split"]

    sig = (
        magnifier_enabled,
        magnifier_models_sig,
        magnifier["visible"],
        magnifier["position"],
        magnifier["size_relative"],
        magnifier["capture_size_relative"],
        offset_for_sig,
        spacing_for_sig,
        internal_split_for_sig,
        combined,
        magnifier["is_horizontal"],
        magnifier["visible_left"],
        magnifier["visible_center"],
        magnifier["visible_right"],
        border_color,
        capture_color,
        guides_state.color,
        guides_state.enabled,
        guides_state.thickness,
        interp_method,
        view.diff_mode,
        view.channel_view_mode,
        divider_visible,
        divider_color,
        divider_thickness,
    )
    return sig

def get_divider_color_tuple(vp):
    dc = _query_overlay_from_viewport(vp, "overlay.active_divider_color")
    if dc is None:
        return (1.0, 1.0, 1.0, 1.0)
    return (dc.r / 255.0, dc.g / 255.0, dc.b / 255.0, dc.a / 255.0)
