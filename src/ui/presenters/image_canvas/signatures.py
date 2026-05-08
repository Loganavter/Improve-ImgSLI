from ui.canvas_features.capture.state import get_capture_widget_state
from ui.canvas_features.guides.state import get_guides_widget_state
from ui.canvas_features.magnifier import MagnifierStoreService
from ui.canvas_features.magnifier.store import (
    active_or_default_border_color,
    active_or_default_divider_color,
    active_or_default_divider_thickness,
    active_or_default_divider_visible,
    magnifier_enabled,
)
from ui.canvas_infra.scene.property_access import read_canvas_feature_property
from ui.canvas_infra.scene.widget_registry import get_canvas_feature_properties

def _get_effective_main_interpolation_method(vp):
    viewport_value = getattr(vp.render_config, "interpolation_method", None)
    if viewport_value:
        return viewport_value
    render_cfg = getattr(vp, "render_config", None)
    return getattr(render_cfg, "interpolation_method", "BILINEAR") if render_cfg else "BILINEAR"

def _magnifier_models_signature(scene_state: MagnifierStoreService):
    models = []
    for model in scene_state.iter_magnifiers():
        models.append(
            (
                model.id,
                bool(model.visible),
                model.position,
                float(model.size_relative),
                float(model.capture_size_relative),
                model.offset_relative,
                float(model.spacing_relative),
                float(model.internal_split),
                bool(model.is_horizontal),
                bool(model.visible_left),
                bool(model.visible_center),
                bool(model.visible_right),
                bool(model.freeze),
                model.frozen_position,
                model.divider_color,
                model.border_color,
                model.laser_color,
                model.capture_ring_color,
            )
        )
    return tuple(models)

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
    scene_state = MagnifierStoreService(presenter.store)
    capture_state = get_capture_widget_state(view)
    guides_state = get_guides_widget_state(view)
    magnifier = scene_state.get_active_or_first_magnifier()
    magnifier_models_sig = _magnifier_models_signature(scene_state)
    feature_props_sig = _canvas_feature_properties_signature(vp)
    if magnifier is None:
        return (
            None,
            feature_props_sig,
            magnifier_models_sig,
            view.split_position_visual,
            magnifier_enabled(view),
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
            active_or_default_divider_thickness(view),
            active_or_default_divider_color(view),
            active_or_default_divider_visible(view),
            active_or_default_border_color(view),
            guides_state.color,
            capture_state.color,
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
            render.magnifier_movement_interpolation_method,
            guides_state.smoothing_interpolation_method,
            view.optimize_magnifier_movement,
            guides_state.smoothing_enabled,
            doc.get_current_display_name(1),
            doc.get_current_display_name(2),
            id(s1),
            id(s2),
        )
    return (
        magnifier.position,
        feature_props_sig,
        magnifier_models_sig,
        magnifier.visible,
        view.split_position_visual,
        magnifier_enabled(view),
        guides_state.enabled,
        guides_state.thickness,
        magnifier.capture_size_relative,
        magnifier.size_relative,
        scene_state.is_active_magnifier_combined(),
        magnifier.internal_split,
        magnifier.is_horizontal,
        view.diff_mode,
        view.channel_view_mode,
        view.is_horizontal,
        magnifier.visible_left,
        magnifier.visible_center,
        magnifier.visible_right,
        active_or_default_divider_thickness(view),
        active_or_default_divider_color(view),
        active_or_default_divider_visible(view),
        active_or_default_border_color(view),
        guides_state.color,
        capture_state.color,
        magnifier.offset_relative,
        magnifier.spacing_relative,
        render.include_file_names_in_saved,
        render.font_size_percent,
        render.font_weight,
        render.text_alpha_percent,
        render.file_name_color,
        render.file_name_bg_color,
        render.draw_text_background,
        render.text_placement_mode,
        render.max_name_length,
        render.magnifier_movement_interpolation_method,
        guides_state.smoothing_interpolation_method,
        view.optimize_magnifier_movement,
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
    scene_state = MagnifierStoreService(presenter.store)
    capture_state = get_capture_widget_state(view)
    guides_state = get_guides_widget_state(view)
    magnifier = scene_state.get_active_or_first_magnifier()
    magnifier_models_sig = _magnifier_models_signature(scene_state)
    if magnifier is None:
        return (magnifier_enabled(view), magnifier_models_sig, None, None)
    interaction = vp.interaction_state
    is_interactive = interaction.is_interactive_mode
    interp_method = (
        render.magnifier_movement_interpolation_method
        if is_interactive
        else _get_effective_main_interpolation_method(vp)
    )

    if is_interactive:
        offset_for_sig = interaction.magnifier_offset_relative_visual
        spacing_for_sig = interaction.magnifier_spacing_relative_visual
        internal_split_for_sig = interaction.magnifier_internal_split_visual
    else:
        offset_for_sig = magnifier.offset_relative
        spacing_for_sig = magnifier.spacing_relative
        internal_split_for_sig = magnifier.internal_split

    sig = (
        magnifier_enabled(view),
        magnifier_models_sig,
        magnifier.visible,
        magnifier.position,
        magnifier.size_relative,
        magnifier.capture_size_relative,
        offset_for_sig,
        spacing_for_sig,
        internal_split_for_sig,
        scene_state.is_active_magnifier_combined(),
        magnifier.is_horizontal,
        magnifier.visible_left,
        magnifier.visible_center,
        magnifier.visible_right,
        active_or_default_border_color(view),
        capture_state.color,
        guides_state.color,
        guides_state.enabled,
        guides_state.thickness,
        interp_method,
        view.diff_mode,
        view.channel_view_mode,
        active_or_default_divider_visible(view),
        active_or_default_divider_color(view),
        active_or_default_divider_thickness(view),
    )
    return sig

def get_divider_color_tuple(vp):
    dc = active_or_default_divider_color(vp.view_state)
    return (dc.r / 255.0, dc.g / 255.0, dc.b / 255.0, dc.a / 255.0)
