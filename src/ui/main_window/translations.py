from __future__ import annotations

from resources.translations import tr
from sli_ui_toolkit.i18n import TranslationsBinder


def build_translations_binder(ui) -> TranslationsBinder:
    """Build a TranslationsBinder wired to all localized widgets of the
    main window. Returned binder reapplies all strings on `apply(lang)`."""
    binder = TranslationsBinder(tr_func=tr)

    binder.bind_callback(
        lambda lang: ui.main_window.setWindowTitle(tr("app.name", lang))
    )

    _bind_labels(binder, ui)
    _bind_placeholders(binder, ui)
    _bind_button_texts(binder, ui)
    _bind_tooltips(binder, ui)
    _bind_group_titles(binder, ui)
    _bind_slider_labels(binder, ui)
    _bind_color_button_updates(binder, ui)

    return binder


def _bind_labels(binder: TranslationsBinder, ui) -> None:
    binder.bind_text(ui.label_edit_name1, "label.name_1", suffix=":")
    binder.bind_text(ui.label_edit_name2, "label.name_2", suffix=":")


def _bind_placeholders(binder: TranslationsBinder, ui) -> None:
    binder.bind_placeholder(ui.edit_name1, "ui.edit_current_image_1_name")
    binder.bind_placeholder(ui.edit_name2, "ui.edit_current_image_2_name")


def _bind_button_texts(binder: TranslationsBinder, ui) -> None:
    binder.bind_text(ui.btn_image1, "button.add_images_1")
    binder.bind_text(ui.btn_image2, "button.add_images_2")
    binder.bind_text(ui.btn_save, "button.save_result")


def _bind_tooltips(binder: TranslationsBinder, ui) -> None:
    simple = [
        (ui.btn_image1, "tooltip.add_images_1"),
        (ui.btn_image2, "tooltip.add_images_2"),
        (ui.btn_text_settings, "tooltip.open_file_name_text_settings"),
        (ui.btn_quick_save, "tooltip.quick_save_image"),
        (ui.btn_save, "tooltip.save_result"),
        (ui.btn_orientation, "ui.toggle_split_orientation"),
        (ui.btn_orientation_simple, "ui.toggle_split_orientation"),
        (ui.btn_magnifier, "magnifier.toggle_magnifier"),
        (ui.btn_magnifier_instances, "tooltip.add_or_remove_magnifier"),
        (ui.btn_freeze, "magnifier.freeze_magnifier_position"),
        (ui.btn_magnifier_orientation, "ui.toggle_split_orientation"),
        (ui.btn_magnifier_orientation_simple, "ui.toggle_split_orientation"),
        (ui.btn_file_names, "ui.include_file_names_in_saved_image"),
        (ui.btn_diff_mode, "tooltip.change_diff_mode"),
        (ui.btn_channel_mode, "tooltip.change_channel_mode"),
        (ui.btn_magnifier_color_settings, "magnifier.change_magnifier_colors"),
        (ui.btn_magnifier_color_settings_beginner, "magnifier.change_magnifier_colors"),
        (ui.btn_magnifier_guides, "magnifier.toggle_magnifier_guide_lines"),
        (ui.btn_magnifier_guides_simple, "magnifier.toggle_magnifier_guide_lines"),
        (ui.btn_divider_visible, "tooltip.toggle_divider_visibility"),
        (ui.btn_divider_color, "ui.choose_divider_line_color"),
        (ui.btn_divider_width, "tooltip.adjust_divider_width"),
        (ui.btn_magnifier_divider_visible, "tooltip.toggle_magnifier_divider_visibility"),
        (ui.btn_magnifier_divider_width, "tooltip.adjust_magnifier_divider_width"),
        (ui.btn_magnifier_guides_width, "tooltip.adjust_magnifier_guides_width"),
        (ui.btn_record, "button.startstop_recording"),
        (ui.btn_pause, "button.pauseresume_recording"),
        (ui.btn_video_editor, "action.open_video_editor_exporter"),
        (ui.btn_new_session, "tooltip.create_workspace_session"),
        (ui.btn_settings, "action.open_application_settings"),
        (ui.help_button, "action.show_help"),
    ]
    for widget, key in simple:
        binder.bind_tooltip(widget, key)

    binder.bind_callback(
        lambda lang: ui.btn_swap.setToolTip(
            f"{tr('tooltip.click_swap_current_images', lang)}\n"
            f"{tr('tooltip.hold_swap_entire_lists', lang)}"
        )
    )

    def _clear_tooltip(lang: str) -> str:
        return (
            f"{tr('tooltip.click_remove_current_image', lang)}\n"
            f"{tr('button.hold_clear_entire_list', lang)}"
        )

    binder.bind_callback(lambda lang: ui.btn_clear_list1.setToolTip(_clear_tooltip(lang)))
    binder.bind_callback(lambda lang: ui.btn_clear_list2.setToolTip(_clear_tooltip(lang)))


def _bind_group_titles(binder: TranslationsBinder, ui) -> None:
    groups = (
        ("line_group_container", "label.line"),
        ("magnifier_group_container", "label.magnifier"),
        ("view_group_container", "label.view"),
        ("record_group_container", "button.record"),
    )

    def _make(attr_name: str, key: str):
        def _apply(lang: str) -> None:
            container = getattr(ui, attr_name, None)
            if container is not None:
                container.set_label_text(tr(key, lang))
        return _apply

    for attr_name, key in groups:
        binder.bind_callback(_make(attr_name, key))


def _bind_slider_labels(binder: TranslationsBinder, ui) -> None:
    binder.bind_text(ui.label_magnifier_size, "label.magnifier_size", suffix=":")
    binder.bind_text(ui.label_capture_size, "label.capture_size", suffix=":")
    binder.bind_text(ui.label_movement_speed, "magnifier.move_speed", suffix=":")
    binder.bind_text(ui.label_interpolation, "magnifier.magnifier_interpolation", suffix=":")


def _bind_color_button_updates(binder: TranslationsBinder, ui) -> None:
    for attr in ("btn_magnifier_color_settings", "btn_magnifier_color_settings_beginner"):
        widget = getattr(ui, attr, None)
        if widget is not None and hasattr(widget, "update_language"):
            binder.bind_callback(lambda lang, w=widget: w.update_language(lang))
