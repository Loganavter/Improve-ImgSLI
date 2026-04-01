def _get_effective_main_interpolation_method(vp):
    viewport_value = getattr(vp.render_config, "interpolation_method", None)
    if viewport_value:
        return viewport_value
    render_cfg = getattr(vp, "render_config", None)
    return getattr(render_cfg, "interpolation_method", "BILINEAR") if render_cfg else "BILINEAR"

def get_render_params_signature(presenter, s1, s2):
    vp = presenter.store.viewport
    view = vp.view_state
    render = vp.render_config
    doc = presenter.store.document
    return (
        view.capture_position_relative,
        view.split_position_visual,
        view.use_magnifier,
        render.show_magnifier_guides,
        render.magnifier_guides_thickness,
        view.capture_size_relative,
        view.magnifier_size_relative,
        view.is_magnifier_combined,
        view.magnifier_internal_split,
        view.magnifier_is_horizontal,
        view.diff_mode,
        view.channel_view_mode,
        view.is_horizontal,
        view.magnifier_visible_left,
        view.magnifier_visible_center,
        view.magnifier_visible_right,
        render.divider_line_thickness,
        render.divider_line_color,
        render.divider_line_visible,
        render.magnifier_divider_thickness,
        render.magnifier_divider_color,
        render.magnifier_divider_visible,
        render.magnifier_border_color,
        render.magnifier_laser_color,
        render.capture_ring_color,
        view.magnifier_offset_relative_visual,
        view.magnifier_spacing_relative_visual,
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
        render.laser_smoothing_interpolation_method,
        view.optimize_magnifier_movement,
        render.optimize_laser_smoothing,
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
    return (
        id(s1),
        id(s2),
        geometry.pixmap_width,
        geometry.pixmap_height,
        view.split_position_visual,
        view.is_horizontal,
        view.diff_mode,
        view.channel_view_mode,
        render.divider_line_thickness,
        render.divider_line_color,
        render.divider_line_visible,
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
    interaction = vp.interaction_state
    is_interactive = interaction.is_interactive_mode
    interp_method = (
        render.magnifier_movement_interpolation_method
        if is_interactive
        else _get_effective_main_interpolation_method(vp)
    )

    if is_interactive:
        offset_for_sig = view.magnifier_offset_relative
        spacing_for_sig = view.magnifier_spacing_relative
    else:
        offset_for_sig = view.magnifier_offset_relative_visual
        spacing_for_sig = view.magnifier_spacing_relative_visual

    sig = (
        view.use_magnifier,
        view.capture_position_relative,
        view.magnifier_size_relative,
        view.capture_size_relative,
        offset_for_sig,
        spacing_for_sig,
        view.magnifier_internal_split,
        view.is_magnifier_combined,
        view.magnifier_is_horizontal,
        view.magnifier_visible_left,
        view.magnifier_visible_center,
        view.magnifier_visible_right,
        render.magnifier_border_color,
        render.capture_ring_color,
        render.magnifier_laser_color,
        render.show_magnifier_guides,
        render.magnifier_guides_thickness,
        interp_method,
        view.diff_mode,
        view.channel_view_mode,
        render.magnifier_divider_visible,
        render.magnifier_divider_color,
        render.magnifier_divider_thickness,
    )
    return sig

def get_divider_color_tuple(vp):
    dc = vp.render_config.magnifier_divider_color
    return (dc.r / 255.0, dc.g / 255.0, dc.b / 255.0, dc.a / 255.0)
