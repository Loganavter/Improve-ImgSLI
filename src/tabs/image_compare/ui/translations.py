from __future__ import annotations

from sli_ui_toolkit.i18n import (
    tr,
    translatable_callback,
    translatable_placeholder,
    translatable_text,
    translatable_tooltip,
)

# Image Compare lives in a QStackedWidget page — skip language fan-out while
# the session picker (or another tab) is current; flush on next Show.
_DEFER = True


def install_image_compare_translations(ui) -> None:
    _bind_labels(ui)
    _bind_placeholders(ui)
    _bind_button_texts(ui)
    _bind_tooltips(ui)
    _bind_group_titles(ui)
    _bind_slider_labels(ui)
    _bind_color_button_updates(ui)


def _bind_labels(ui) -> None:
    translatable_text(
        ui.label_edit_name1, "label.name_1", suffix=":", defer_when_hidden=_DEFER
    )
    translatable_text(
        ui.label_edit_name2, "label.name_2", suffix=":", defer_when_hidden=_DEFER
    )


def _bind_placeholders(ui) -> None:
    translatable_placeholder(
        ui.edit_name1, "ui.edit_current_image_1_name", defer_when_hidden=_DEFER
    )
    translatable_placeholder(
        ui.edit_name2, "ui.edit_current_image_2_name", defer_when_hidden=_DEFER
    )


def _bind_button_texts(ui) -> None:
    translatable_text(
        ui.btn_image1, "button.add_images_1", defer_when_hidden=_DEFER
    )
    translatable_text(
        ui.btn_image2, "button.add_images_2", defer_when_hidden=_DEFER
    )
    translatable_text(
        ui.btn_save, "button.save_result", defer_when_hidden=_DEFER
    )


def _bind_tooltips(ui) -> None:
    simple = [
        (ui.btn_image1, "tooltip.add_images_1"),
        (ui.btn_image2, "tooltip.add_images_2"),
        (ui.btn_text_settings, "tooltip.open_file_name_text_settings"),
        (ui.btn_quick_save, "tooltip.quick_save_image"),
        (ui.btn_save, "tooltip.save_result"),
        (ui.btn_orientation, "image_compare.action.divider_combined_desc"),
        (ui.btn_orientation_simple, "tooltip.split_orientation"),
        (ui.btn_magnifier, "tooltip.toggle_magnifier"),
        (ui.btn_magnifier_instances, "tooltip.add_or_remove_magnifier"),
        (ui.btn_freeze, "tooltip.freeze_magnifier_position"),
        (ui.btn_magnifier_orientation, "image_compare.action.magnifier_divider_combined_desc"),
        (ui.btn_magnifier_orientation_simple, "tooltip.magnifier_orientation"),
        (ui.btn_file_names, "tooltip.include_file_names"),
        (ui.btn_diff_mode, "tooltip.change_diff_mode"),
        (ui.btn_channel_mode, "tooltip.change_channel_mode"),
        (ui.btn_magnifier_color_settings, "tooltip.magnifier_colors"),
        (ui.btn_magnifier_color_settings_beginner, "tooltip.magnifier_colors"),
        (ui.btn_magnifier_guides, "tooltip.magnifier_guides"),
        (ui.btn_magnifier_guides_simple, "tooltip.magnifier_guides"),
        (ui.btn_divider_visible, "tooltip.toggle_divider_visibility"),
        (ui.btn_divider_color, "tooltip.divider_color"),
        (ui.btn_divider_width, "tooltip.adjust_divider_width"),
        (
            ui.btn_magnifier_divider_visible,
            "tooltip.toggle_magnifier_divider_visibility",
        ),
        (ui.btn_magnifier_divider_width, "tooltip.adjust_magnifier_divider_width"),
        (ui.btn_magnifier_guides_width, "tooltip.adjust_magnifier_guides_width"),
        (ui.btn_record, "tooltip.record_video"),
        (ui.btn_pause, "tooltip.pause_recording"),
        (ui.btn_video_editor, "tooltip.open_video_editor"),
        (ui.btn_settings, "tooltip.open_application_settings"),
        (ui.help_button, "tooltip.show_help"),
        (ui.combo_interpolation, "tooltip.magnifier_interpolation"),
        (ui.btn_zoom_reset, "tooltip.reset_zoom"),
    ]
    for widget, key in simple:
        translatable_tooltip(widget, key, defer_when_hidden=_DEFER)

    translatable_callback(
        ui.btn_swap,
        lambda lang: ui.btn_swap.setToolTip(
            f"{tr('tooltip.click_swap_current_images', lang)}\n"
            f"{tr('tooltip.hold_swap_entire_lists', lang)}"
        ),
        defer_when_hidden=_DEFER,
    )

    def _clear_tooltip(lang: str) -> str:
        return (
            f"{tr('tooltip.click_remove_current_image', lang)}\n"
            f"{tr('button.hold_clear_entire_list', lang)}"
        )

    translatable_callback(
        ui.btn_clear_list1,
        lambda lang: ui.btn_clear_list1.setToolTip(_clear_tooltip(lang)),
        defer_when_hidden=_DEFER,
    )
    translatable_callback(
        ui.btn_clear_list2,
        lambda lang: ui.btn_clear_list2.setToolTip(_clear_tooltip(lang)),
        defer_when_hidden=_DEFER,
    )


def _bind_group_titles(ui) -> None:
    groups = (
        ("line_group_container", "label.line"),
        ("magnifier_group_container", "label.magnifier"),
        ("view_group_container", "label.view"),
        ("record_group_container", "button.record"),
    )
    for attr_name, key in groups:
        container = getattr(ui, attr_name)
        translatable_callback(
            container,
            lambda lang, c=container, k=key: c.set_label_text(tr(k, lang)),
            defer_when_hidden=_DEFER,
        )


def _bind_slider_labels(ui) -> None:
    translatable_text(
        ui.label_magnifier_size,
        "label.magnifier_size",
        suffix=":",
        defer_when_hidden=_DEFER,
    )
    translatable_text(
        ui.label_capture_size,
        "label.capture_size",
        suffix=":",
        defer_when_hidden=_DEFER,
    )
    translatable_text(
        ui.label_movement_speed,
        "magnifier.move_speed",
        suffix=":",
        defer_when_hidden=_DEFER,
    )
    translatable_text(
        ui.label_interpolation,
        "magnifier.magnifier_interpolation",
        suffix=":",
        defer_when_hidden=_DEFER,
    )


def _bind_color_button_updates(ui) -> None:
    for attr in (
        "btn_magnifier_color_settings",
        "btn_magnifier_color_settings_beginner",
    ):
        widget = getattr(ui, attr)
        translatable_callback(
            widget, widget.update_language, defer_when_hidden=_DEFER
        )
