def _get_effective_main_interpolation_method(vp):
    viewport_value = getattr(vp, "interpolation_method", None)
    if viewport_value:
        return viewport_value
    render_cfg = getattr(vp, "render_config", None)
    return getattr(render_cfg, "interpolation_method", "BILINEAR") if render_cfg else "BILINEAR"

def get_render_params_signature(presenter, s1, s2):
    vp = presenter.store.viewport
    doc = presenter.store.document
    return (
        vp.capture_position_relative,
        vp.split_position_visual,
        vp.use_magnifier,
        vp.show_magnifier_guides,
        vp.magnifier_guides_thickness,
        vp.capture_size_relative,
        vp.magnifier_size_relative,
        vp.is_magnifier_combined,
        vp.magnifier_internal_split,
        vp.magnifier_is_horizontal,
        vp.diff_mode,
        vp.channel_view_mode,
        vp.is_horizontal,
        vp.magnifier_visible_left,
        vp.magnifier_visible_center,
        vp.magnifier_visible_right,
        vp.divider_line_thickness,
        vp.divider_line_color,
        vp.divider_line_visible,
        vp.magnifier_divider_thickness,
        vp.magnifier_divider_color,
        vp.magnifier_divider_visible,
        vp.magnifier_border_color,
        vp.magnifier_laser_color,
        vp.capture_ring_color,
        vp.magnifier_offset_relative_visual,
        vp.magnifier_spacing_relative_visual,
        vp.include_file_names_in_saved,
        vp.font_size_percent,
        vp.font_weight,
        vp.text_alpha_percent,
        vp.file_name_color,
        vp.file_name_bg_color,
        vp.draw_text_background,
        vp.text_placement_mode,
        vp.max_name_length,
        vp.render_config.magnifier_movement_interpolation_method,
        vp.render_config.laser_smoothing_interpolation_method,
        vp.optimize_magnifier_movement,
        vp.optimize_laser_smoothing,
        doc.get_current_display_name(1),
        doc.get_current_display_name(2),
        id(s1),
        id(s2),
    )

def get_background_signature(presenter, s1, s2):
    vp = presenter.store.viewport
    doc = presenter.store.document
    return (
        id(s1),
        id(s2),
        vp.pixmap_width,
        vp.pixmap_height,
        vp.split_position_visual,
        vp.is_horizontal,
        vp.diff_mode,
        vp.channel_view_mode,
        vp.divider_line_thickness,
        vp.divider_line_color,
        vp.divider_line_visible,
        vp.include_file_names_in_saved,
        doc.get_current_display_name(1),
        doc.get_current_display_name(2),
        vp.font_size_percent,
        vp.font_weight,
        vp.text_alpha_percent,
        vp.file_name_color,
        vp.file_name_bg_color,
        vp.draw_text_background,
        vp.text_placement_mode,
        vp.max_name_length,
    )

def get_magnifier_signature(presenter):
    vp = presenter.store.viewport
    is_interactive = vp.is_interactive_mode
    interp_method = (
        vp.render_config.magnifier_movement_interpolation_method
        if is_interactive
        else _get_effective_main_interpolation_method(vp)
    )

    if is_interactive:
        offset_for_sig = vp.magnifier_offset_relative
        spacing_for_sig = vp.magnifier_spacing_relative
    else:
        offset_for_sig = vp.magnifier_offset_relative_visual
        spacing_for_sig = vp.magnifier_spacing_relative_visual

    sig = (
        vp.use_magnifier,
        vp.capture_position_relative,
        vp.magnifier_size_relative,
        vp.capture_size_relative,
        offset_for_sig,
        spacing_for_sig,
        vp.magnifier_internal_split,
        vp.is_magnifier_combined,
        vp.magnifier_is_horizontal,
        vp.magnifier_visible_left,
        vp.magnifier_visible_center,
        vp.magnifier_visible_right,
        vp.magnifier_border_color,
        vp.capture_ring_color,
        vp.magnifier_laser_color,
        vp.show_magnifier_guides,
        vp.magnifier_guides_thickness,
        interp_method,
        vp.diff_mode,
        vp.channel_view_mode,
        vp.magnifier_divider_visible,
        vp.magnifier_divider_color,
        vp.magnifier_divider_thickness,
    )
    return sig

def get_divider_color_tuple(vp):
    dc = vp.magnifier_divider_color
    return (dc.r / 255.0, dc.g / 255.0, dc.b / 255.0, dc.a / 255.0)
