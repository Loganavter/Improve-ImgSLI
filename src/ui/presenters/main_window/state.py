from PyQt6.QtCore import QTimer

from domain.qt_adapters import color_to_qcolor
from resources.translations import tr

def apply_initial_settings_to_ui(presenter):
    ui = presenter.ui
    viewport = presenter.store.viewport
    settings = presenter.store.settings

    ui.slider_size.setValue(int(viewport.view_state.magnifier_size_relative * 100))
    ui.slider_capture.setValue(int(viewport.view_state.capture_size_relative * 100))
    ui.slider_speed.setValue(int(viewport.view_state.movement_speed_per_sec * 10))

    divider_thickness = 0 if not viewport.render_config.divider_line_visible else viewport.render_config.divider_line_thickness
    magnifier_thickness = (
        0
        if not viewport.render_config.magnifier_divider_visible
        else viewport.render_config.magnifier_divider_thickness
    )

    ui.btn_orientation.set_value(divider_thickness)
    ui.btn_magnifier_orientation.set_value(magnifier_thickness)
    ui.btn_orientation.setChecked(viewport.view_state.is_horizontal, emit_signal=False)
    ui.btn_magnifier_orientation.setChecked(
        viewport.view_state.magnifier_is_horizontal, emit_signal=False
    )

    if hasattr(ui, "btn_orientation_simple"):
        ui.btn_orientation_simple.setChecked(viewport.view_state.is_horizontal, emit_signal=False)
    if hasattr(ui, "btn_divider_visible"):
        ui.btn_divider_visible.setChecked(
            not viewport.render_config.divider_line_visible, emit_signal=False
        )
    if hasattr(ui, "btn_divider_width"):
        ui.btn_divider_width.set_value(divider_thickness)
    if hasattr(ui, "btn_divider_color") and hasattr(ui.btn_divider_color, "set_color"):
        ui.btn_divider_color.set_color(color_to_qcolor(viewport.render_config.divider_line_color))
    if hasattr(ui, "btn_magnifier_orientation_simple"):
        ui.btn_magnifier_orientation_simple.setChecked(
            viewport.view_state.magnifier_is_horizontal, emit_signal=False
        )
    if hasattr(ui, "btn_magnifier_divider_visible"):
        ui.btn_magnifier_divider_visible.setChecked(
            not viewport.render_config.magnifier_divider_visible, emit_signal=False
        )
    if hasattr(ui, "btn_magnifier_divider_width"):
        ui.btn_magnifier_divider_width.set_value(magnifier_thickness)
    if hasattr(ui, "btn_magnifier_guides_simple"):
        ui.btn_magnifier_guides_simple.setChecked(
            viewport.render_config.show_magnifier_guides, emit_signal=False
        )
    if hasattr(ui, "btn_magnifier_guides_width"):
        ui.btn_magnifier_guides_width.set_value(viewport.render_config.magnifier_guides_thickness)

    ui.btn_magnifier.setChecked(viewport.view_state.use_magnifier, emit_signal=False)
    ui.btn_freeze.setChecked(viewport.view_state.freeze_magnifier, emit_signal=False)
    ui.btn_magnifier_guides.setChecked(
        viewport.render_config.show_magnifier_guides, emit_signal=False
    )
    ui.btn_magnifier_guides.set_value(viewport.render_config.magnifier_guides_thickness)
    ui.btn_file_names.setChecked(viewport.render_config.include_file_names_in_saved, emit_signal=False)

    _apply_mode_specific_colors(presenter)
    ui.toggle_edit_layout_visibility(viewport.render_config.include_file_names_in_saved)
    ui.toggle_magnifier_panel_visibility(viewport.view_state.use_magnifier)

    if presenter.font_settings_flyout:
        presenter.font_settings_flyout.set_values(
            viewport.render_config.font_size_percent,
            viewport.render_config.font_weight,
            color_to_qcolor(viewport.render_config.file_name_color),
            color_to_qcolor(viewport.render_config.file_name_bg_color),
            viewport.render_config.draw_text_background,
            viewport.render_config.text_placement_mode,
            viewport.render_config.text_alpha_percent,
            settings.current_language,
        )

    settings_presenter = presenter.get_feature("settings")
    settings_presenter.update_interpolation_combo_box_ui()
    settings_presenter.setup_view_buttons()
    do_update_file_names_display(presenter)
    on_language_changed(presenter)

def on_store_state_changed(presenter, domain: str):
    is_viewport_domain = domain == "viewport" or domain.startswith("viewport.")

    if domain == "workspace":
        from ui.presenters.main_window.workspace import (
            sync_session_mode,
            sync_video_session_view,
            sync_workspace_tabs,
        )

        sync_workspace_tabs(presenter)
        sync_session_mode(presenter)
        sync_video_session_view(presenter)
        presenter.ui_batcher.schedule_batch_update(
            ["file_names", "resolution", "combobox", "slider_tooltips", "ratings", "window_schedule"]
        )
        return

    if not is_viewport_domain and domain not in ("document", "settings"):
        return

    viewport_subdomain = domain.split(".", 1)[1] if is_viewport_domain and "." in domain else None
    if viewport_subdomain in {"interaction", "geometry"}:
        return

    if domain == "settings":
        _apply_orientation_underline_mode(presenter)

    ui = presenter.ui
    viewport = presenter.store.viewport
    ui.toggle_magnifier_panel_visibility(viewport.view_state.use_magnifier)

    if ui.btn_orientation.isChecked() != viewport.view_state.is_horizontal:
        ui.btn_orientation.setChecked(viewport.view_state.is_horizontal, emit_signal=False)
    if ui.btn_magnifier_orientation.isChecked() != viewport.view_state.magnifier_is_horizontal:
        ui.btn_magnifier_orientation.setChecked(
            viewport.view_state.magnifier_is_horizontal, emit_signal=False
        )

    divider_thickness = 0 if not viewport.render_config.divider_line_visible else viewport.render_config.divider_line_thickness
    magnifier_thickness = (
        0 if not viewport.render_config.magnifier_divider_visible else viewport.render_config.magnifier_divider_thickness
    )
    if ui.btn_orientation.get_value() != divider_thickness:
        ui.btn_orientation.set_value(divider_thickness)
    if ui.btn_magnifier_orientation.get_value() != magnifier_thickness:
        ui.btn_magnifier_orientation.set_value(magnifier_thickness)

    if ui.btn_magnifier_guides.isChecked() != viewport.render_config.show_magnifier_guides:
        ui.btn_magnifier_guides.setChecked(viewport.render_config.show_magnifier_guides, emit_signal=False)
    if ui.btn_magnifier_guides.get_value() != viewport.render_config.magnifier_guides_thickness:
        ui.btn_magnifier_guides.set_value(viewport.render_config.magnifier_guides_thickness)

    _apply_mode_specific_colors(presenter)

    if hasattr(ui, "btn_divider_visible"):
        should_be_checked = not viewport.render_config.divider_line_visible
        if ui.btn_divider_visible.isChecked() != should_be_checked:
            ui.btn_divider_visible.setChecked(should_be_checked, emit_signal=False)

    if hasattr(ui, "btn_magnifier_divider_visible"):
        should_be_checked = not viewport.render_config.magnifier_divider_visible
        if ui.btn_magnifier_divider_visible.isChecked() != should_be_checked:
            ui.btn_magnifier_divider_visible.setChecked(
                should_be_checked, emit_signal=False
            )

    if hasattr(ui, "btn_magnifier_guides_simple"):
        if ui.btn_magnifier_guides_simple.isChecked() != viewport.render_config.show_magnifier_guides:
            ui.btn_magnifier_guides_simple.setChecked(
                viewport.render_config.show_magnifier_guides, emit_signal=False
            )
    if hasattr(ui, "btn_magnifier_guides_width"):
        if ui.btn_magnifier_guides_width.get_value() != viewport.render_config.magnifier_guides_thickness:
            ui.btn_magnifier_guides_width.set_value(viewport.render_config.magnifier_guides_thickness)

    ui.toggle_edit_layout_visibility(viewport.render_config.include_file_names_in_saved)
    presenter.ui_batcher.schedule_batch_update(
        ["file_names", "resolution", "combobox", "slider_tooltips", "ratings", "window_schedule"]
    )

def do_update_resolution_labels(presenter):
    has_both_images = bool(
        presenter.store.document.image1_path and presenter.store.document.image2_path
    )

    res1_text = ""
    res2_text = ""
    if has_both_images:
        if dim := get_image_dimensions(presenter, 1):
            res1_text = f"{dim[0]}x{dim[1]}"
        if dim := get_image_dimensions(presenter, 2):
            res2_text = f"{dim[0]}x{dim[1]}"
    presenter.ui.update_resolution_labels(res1_text, res1_text, res2_text, res2_text)

    psnr_visible = presenter.store.viewport.session_data.image_state.auto_calculate_psnr
    presenter.ui.psnr_label.setVisible(psnr_visible)
    if psnr_visible:
        psnr = presenter.store.viewport.session_data.image_state.psnr_value
        if psnr is not None:
            presenter.ui.psnr_label.setText(
                f"{tr('ui.psnr', presenter.store.settings.current_language)}: {psnr:.2f} dB"
            )
        else:
            presenter.ui.psnr_label.setText(
                f"{tr('ui.psnr', presenter.store.settings.current_language)}: --"
            )

    ssim_visible = (
        presenter.store.viewport.session_data.image_state.auto_calculate_ssim
        or presenter.store.viewport.view_state.diff_mode == "ssim"
    )
    presenter.ui.ssim_label.setVisible(ssim_visible)
    if ssim_visible:
        ssim = presenter.store.viewport.session_data.image_state.ssim_value
        if ssim is not None:
            presenter.ui.ssim_label.setText(
                f"{tr('ui.ssim', presenter.store.settings.current_language)}: {ssim:.4f}"
            )
        else:
            presenter.ui.ssim_label.setText(
                f"{tr('ui.ssim', presenter.store.settings.current_language)}: --"
            )

def do_update_file_names_display(presenter):
    name1 = presenter.store.document.get_current_display_name(1) or "-----"
    name2 = presenter.store.document.get_current_display_name(2) or "-----"
    lang = presenter.store.settings.current_language
    show_labels = bool(name1 != "-----" or name2 != "-----")

    presenter.ui.update_file_names_display(
        name1_text=name1,
        name2_text=name2,
        is_horizontal=presenter.store.viewport.view_state.is_horizontal,
        current_language=lang,
        show_labels=show_labels,
    )

    if hasattr(presenter.ui, "edit_name1") and not presenter.ui.edit_name1.hasFocus():
        presenter.ui.edit_name1.blockSignals(True)
        display_name1 = presenter.store.document.get_current_display_name(1)
        presenter.ui.edit_name1.setText(display_name1 or "")
        presenter.ui.edit_name1.setCursorPosition(0)
        presenter.ui.edit_name1.blockSignals(False)

    if hasattr(presenter.ui, "edit_name2") and not presenter.ui.edit_name2.hasFocus():
        presenter.ui.edit_name2.blockSignals(True)
        display_name2 = presenter.store.document.get_current_display_name(2)
        presenter.ui.edit_name2.setText(display_name2 or "")
        presenter.ui.edit_name2.setCursorPosition(0)
        presenter.ui.edit_name2.blockSignals(False)

    presenter.check_name_lengths()

def do_update_combobox_displays(presenter):
    count1 = len(presenter.store.document.image_list1)
    idx1 = presenter.store.document.current_index1
    text1 = (
        get_current_display_name(presenter, 1)
        if 0 <= idx1 < count1
        else tr("misc.select_an_image", presenter.store.settings.current_language)
    )
    presenter.ui.update_combobox_display(1, count1, idx1, text1, "")

    count2 = len(presenter.store.document.image_list2)
    idx2 = presenter.store.document.current_index2
    text2 = (
        get_current_display_name(presenter, 2)
        if 0 <= idx2 < count2
        else tr("misc.select_an_image", presenter.store.settings.current_language)
    )
    presenter.ui.update_combobox_display(2, count2, idx2, text2, "")

    if presenter.ui_manager and presenter.ui_manager.transient.unified_flyout.isVisible():
        presenter.ui_manager.transient.unified_flyout.sync_from_store()

def do_update_slider_tooltips(presenter):
    presenter.ui.update_slider_tooltips(
        presenter.store.viewport.view_state.movement_speed_per_sec,
        presenter.store.viewport.view_state.magnifier_size_relative,
        presenter.store.viewport.view_state.capture_size_relative,
        presenter.store.settings.current_language,
    )

def do_update_rating_displays(presenter):
    presenter.ui.update_rating_display(
        1, get_current_score(presenter, 1), presenter.store.settings.current_language
    )
    presenter.ui.update_rating_display(
        2, get_current_score(presenter, 2), presenter.store.settings.current_language
    )

    if presenter.ui_manager and presenter.ui_manager.transient.unified_flyout.isVisible():
        current_idx1 = presenter.store.document.current_index1
        current_idx2 = presenter.store.document.current_index2
        if current_idx1 >= 0:
            presenter.ui_manager.transient.unified_flyout.update_rating_for_item(1, current_idx1)
        if current_idx2 >= 0:
            presenter.ui_manager.transient.unified_flyout.update_rating_for_item(2, current_idx2)
        QTimer.singleShot(0, presenter.ui_manager.transient.unified_flyout.refreshGeometry)

def on_language_changed(presenter):
    lang_code = presenter.store.settings.current_language
    presenter.ui.update_translations(lang_code)
    presenter.get_feature("settings").on_language_changed()
    if (
        hasattr(presenter.main_window_app, "tray_manager")
        and presenter.main_window_app.tray_manager
    ):
        presenter.main_window_app.tray_manager.update_language(lang_code)
    dialogs = getattr(getattr(presenter, "ui_manager", None), "dialogs", None)
    settings_dialog = getattr(dialogs, "settings_dialog", None) if dialogs else None
    if settings_dialog is not None:
        settings_dialog.update_language(lang_code)
    do_update_combobox_displays(presenter)
    do_update_slider_tooltips(presenter)
    do_update_rating_displays(presenter)
    do_update_file_names_display(presenter)
    presenter.repopulate_flyouts()
    presenter.ui.reapply_button_styles()

def get_current_display_name(presenter, image_number: int) -> str:
    return presenter.store.document.get_current_display_name(image_number)

def get_current_score(presenter, image_number: int) -> int | None:
    target_list, index = (
        (presenter.store.document.image_list1, presenter.store.document.current_index1)
        if image_number == 1
        else (presenter.store.document.image_list2, presenter.store.document.current_index2)
    )
    if 0 <= index < len(target_list):
        return target_list[index].rating
    return None

def get_image_dimensions(presenter, image_number: int) -> tuple[int, int] | None:
    if image_number == 1:
        if not presenter.store.document.image1_path:
            return None
        img = presenter.store.document.full_res_image1 or presenter.store.document.preview_image1
    else:
        if not presenter.store.document.image2_path:
            return None
        img = presenter.store.document.full_res_image2 or presenter.store.document.preview_image2
    if img and hasattr(img, "size"):
        return img.size
    return None

def _apply_mode_specific_colors(presenter):
    viewport = presenter.store.viewport
    ui = presenter.ui
    _apply_orientation_underline_mode(presenter)

    if hasattr(ui.btn_orientation, "set_color"):
        show_divider_underline = (
            getattr(viewport.render_config, "divider_line_visible", True)
            and getattr(viewport.render_config, "divider_line_thickness", 0) > 0
        )
        ui.btn_orientation.set_color(
            color_to_qcolor(viewport.render_config.divider_line_color)
            if show_divider_underline
            else None
        )
    if hasattr(ui.btn_magnifier_orientation, "set_color"):
        ui.btn_magnifier_orientation.set_color(
            color_to_qcolor(viewport.render_config.magnifier_divider_color)
        )
    if hasattr(ui, "btn_divider_color") and hasattr(ui.btn_divider_color, "set_color"):
        ui.btn_divider_color.set_color(color_to_qcolor(viewport.render_config.divider_line_color))
    if hasattr(ui, "btn_magnifier_color_settings") and hasattr(
        ui.btn_magnifier_color_settings, "refresh_visual_state"
    ):
        ui.btn_magnifier_color_settings.refresh_visual_state()
    if hasattr(ui, "btn_magnifier_color_settings_beginner") and hasattr(
        ui.btn_magnifier_color_settings_beginner, "refresh_visual_state"
    ):
        ui.btn_magnifier_color_settings_beginner.refresh_visual_state()

def _apply_orientation_underline_mode(presenter):
    current_mode = getattr(presenter.store.settings, "ui_mode", "beginner")
    if hasattr(presenter.ui.btn_orientation, "set_show_underline"):
        presenter.ui.btn_orientation.set_show_underline(current_mode != "advanced")
