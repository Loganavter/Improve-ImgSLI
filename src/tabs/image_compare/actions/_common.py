"""Shared constants, spec tuples, and helpers for image_compare actions."""

from __future__ import annotations

from dataclasses import dataclass

OWNER = "image_compare"

_BC_TOOLBAR = "image_compare.action.breadcrumb.toolbar"
_BC_MAGNIFIER = "image_compare.action.breadcrumb.magnifier"
_BC_SESSION = "image_compare.action.breadcrumb.session"
_BC_LABELS = "image_compare.action.breadcrumb.labels"
_BC_EXPORT = "image_compare.action.breadcrumb.export"
_BC_DIVIDER = "image_compare.action.breadcrumb.divider"
_BC_ANALYSIS = "image_compare.action.breadcrumb.analysis"
_BC_VIDEO = "image_compare.action.breadcrumb.video"

_TOPIC_HELP: dict[str, str] = {
    "magnifier": "magnifier",
    "session": "file_management",
    "labels": "comparison",
    "divider": "comparison",
    "analysis": "comparison",
    "export": "export",
    "video": "video",
}


@dataclass(frozen=True, slots=True)
class _WidgetAction:
    action_id: str
    attr: str
    label_key: str
    description_key: str | None
    breadcrumb: tuple[str, ...]
    topic: str
    kind: str = "toggle"  # toggle | click | short_click
    help_page: str | None = None
    shortcut: str | None = None
    search_keys: tuple[str, ...] = ()
    search_terms: tuple[str, ...] = ()


def _toggle_button(button) -> None:
    if button is None:
        return
    if hasattr(button, "isChecked") and hasattr(button, "setChecked"):
        button.setChecked(not bool(button.isChecked()))
        return
    _click_button(button)


def _click_button(button) -> None:
    if button is None:
        return
    click = getattr(button, "click", None)
    if callable(click):
        click()
        return
    activate = getattr(button, "_activate_via_keyboard", None)
    if callable(activate):
        activate()
        return
    clicked = getattr(button, "clicked", None)
    if clicked is not None and hasattr(clicked, "emit"):
        clicked.emit()


def _short_click_button(button) -> None:
    if button is None:
        return
    short = getattr(button, "shortClicked", None)
    if short is not None and hasattr(short, "emit"):
        short.emit()
        return
    _click_button(button)


# Mode-picker toolbar buttons: shortcuts cycle; mouse click still opens the menu.
_PICKER_CYCLE: dict[str, str] = {
    "btn_channel_mode": "btn_channel_mode_picker",
    "btn_diff_mode": "btn_diff_mode_picker",
}


def _help_for(topic: str, explicit: str | None = None) -> str | None:
    if explicit is not None:
        return explicit
    return _TOPIC_HELP.get(topic)


# ---------------------------------------------------------------------------
# Spec tuples — pure data, no logic
# ---------------------------------------------------------------------------

_SPECS: tuple[_WidgetAction, ...] = (
    _WidgetAction(
        "image_compare.magnifier.enabled",
        "btn_magnifier",
        "image_compare.action.magnifier",
        "tooltip.toggle_magnifier",
        (_BC_TOOLBAR, _BC_MAGNIFIER),
        "magnifier",
        shortcut="M",
    ),
    _WidgetAction(
        "image_compare.magnifier.freeze",
        "btn_freeze",
        "image_compare.action.freeze",
        "tooltip.freeze_magnifier_position",
        (_BC_TOOLBAR, _BC_MAGNIFIER),
        "magnifier",
        shortcut="F",
    ),
    _WidgetAction(
        "image_compare.magnifier.orientation",
        "btn_magnifier_orientation",
        "image_compare.action.magnifier_divider_combined",
        "image_compare.action.magnifier_divider_combined_desc",
        (_BC_TOOLBAR, _BC_MAGNIFIER),
        "magnifier",
        "toggle",
    ),
    _WidgetAction(
        "image_compare.magnifier.orientation_simple",
        "btn_magnifier_orientation_simple",
        "image_compare.action.magnifier_orientation",
        "tooltip.magnifier_orientation",
        (_BC_TOOLBAR, _BC_MAGNIFIER),
        "magnifier",
        "toggle",
    ),
    _WidgetAction(
        "image_compare.magnifier.guides",
        "btn_magnifier_guides",
        "image_compare.action.magnifier_guides",
        "tooltip.magnifier_guides",
        (_BC_TOOLBAR, _BC_MAGNIFIER),
        "magnifier",
        "toggle",
    ),
    _WidgetAction(
        "image_compare.magnifier.guides_simple",
        "btn_magnifier_guides_simple",
        "image_compare.action.magnifier_guides",
        "tooltip.magnifier_guides",
        (_BC_TOOLBAR, _BC_MAGNIFIER),
        "magnifier",
        "toggle",
    ),
    _WidgetAction(
        "image_compare.magnifier.divider_visible",
        "btn_magnifier_divider_visible",
        "image_compare.action.magnifier_divider_visible",
        "tooltip.toggle_magnifier_divider_visibility",
        (_BC_TOOLBAR, _BC_MAGNIFIER),
        "magnifier",
        "toggle",
    ),
    _WidgetAction(
        "image_compare.magnifier.color_settings",
        "btn_magnifier_color_settings",
        "image_compare.action.magnifier_colors",
        "tooltip.magnifier_colors",
        (_BC_TOOLBAR, _BC_MAGNIFIER),
        "magnifier",
        "click",
    ),
    _WidgetAction(
        "image_compare.magnifier.color_settings_beginner",
        "btn_magnifier_color_settings_beginner",
        "image_compare.action.magnifier_colors",
        "tooltip.magnifier_colors",
        (_BC_TOOLBAR, _BC_MAGNIFIER),
        "magnifier",
        "click",
    ),
    _WidgetAction(
        "image_compare.magnifier.instances",
        "btn_magnifier_instances",
        "image_compare.action.magnifier_instances",
        "tooltip.add_or_remove_magnifier",
        (_BC_TOOLBAR, _BC_MAGNIFIER),
        "magnifier",
        "click",
    ),
    _WidgetAction(
        "image_compare.magnifier.divider_width",
        "btn_magnifier_divider_width",
        "image_compare.action.magnifier_divider_width",
        "tooltip.adjust_magnifier_divider_width",
        (_BC_TOOLBAR, _BC_MAGNIFIER),
        "magnifier",
        "click",
    ),
    _WidgetAction(
        "image_compare.magnifier.guides_width",
        "btn_magnifier_guides_width",
        "image_compare.action.magnifier_guides_width",
        "tooltip.adjust_magnifier_guides_width",
        (_BC_TOOLBAR, _BC_MAGNIFIER),
        "magnifier",
        "click",
    ),
    _WidgetAction(
        "image_compare.swap",
        "btn_swap",
        "image_compare.action.swap",
        "tooltip.click_swap_current_images",
        (_BC_TOOLBAR, _BC_SESSION),
        "session",
        "short_click",
        shortcut="X",
    ),
    _WidgetAction(
        "image_compare.clear_list1",
        "btn_clear_list1",
        "image_compare.action.clear_list1",
        "tooltip.click_remove_current_image",
        (_BC_TOOLBAR, _BC_SESSION),
        "session",
        "short_click",
    ),
    _WidgetAction(
        "image_compare.clear_list2",
        "btn_clear_list2",
        "image_compare.action.clear_list2",
        "tooltip.click_remove_current_image",
        (_BC_TOOLBAR, _BC_SESSION),
        "session",
        "short_click",
    ),
    _WidgetAction(
        "image_compare.add_image1",
        "btn_image1",
        "image_compare.action.add_image1",
        "tooltip.add_images_1",
        (_BC_TOOLBAR, _BC_SESSION),
        "session",
        "click",
    ),
    _WidgetAction(
        "image_compare.add_image2",
        "btn_image2",
        "image_compare.action.add_image2",
        "tooltip.add_images_2",
        (_BC_TOOLBAR, _BC_SESSION),
        "session",
        "click",
    ),
    _WidgetAction(
        "image_compare.filename_overlay",
        "btn_file_names",
        "image_compare.action.file_names",
        "image_compare.action.file_names_desc",
        (_BC_TOOLBAR, _BC_LABELS),
        "labels",
        shortcut="N",
    ),
    _WidgetAction(
        "image_compare.text_settings",
        "btn_text_settings",
        "image_compare.action.text_settings",
        "tooltip.open_file_name_text_settings",
        (_BC_TOOLBAR, _BC_LABELS),
        "labels",
        "click",
    ),
    _WidgetAction(
        "image_compare.divider.orientation",
        "btn_orientation",
        "image_compare.action.divider_combined",
        "image_compare.action.divider_combined_desc",
        (_BC_TOOLBAR, _BC_DIVIDER),
        "divider",
        "toggle",
    ),
    _WidgetAction(
        "image_compare.divider.orientation_simple",
        "btn_orientation_simple",
        "image_compare.action.divider_orientation",
        "tooltip.split_orientation",
        (_BC_TOOLBAR, _BC_DIVIDER),
        "divider",
        "toggle",
    ),
    _WidgetAction(
        "image_compare.divider.visible",
        "btn_divider_visible",
        "image_compare.action.divider_visible",
        "tooltip.toggle_divider_visibility",
        (_BC_TOOLBAR, _BC_DIVIDER),
        "divider",
        "toggle",
        shortcut="D",
    ),
    _WidgetAction(
        "image_compare.divider.color",
        "btn_divider_color",
        "image_compare.action.divider_color",
        "tooltip.divider_color",
        (_BC_TOOLBAR, _BC_DIVIDER),
        "divider",
        "click",
    ),
    _WidgetAction(
        "image_compare.divider.width",
        "btn_divider_width",
        "image_compare.action.divider_width",
        "tooltip.adjust_divider_width",
        (_BC_TOOLBAR, _BC_DIVIDER),
        "divider",
        "click",
    ),
    _WidgetAction(
        "image_compare.diff_mode",
        "btn_diff_mode",
        "image_compare.action.diff_mode",
        "tooltip.change_diff_mode",
        (_BC_TOOLBAR, _BC_ANALYSIS),
        "analysis",
        "click",
        shortcut="H",
    ),
    _WidgetAction(
        "image_compare.channel_mode",
        "btn_channel_mode",
        "image_compare.action.channel_mode",
        "tooltip.change_channel_mode",
        (_BC_TOOLBAR, _BC_ANALYSIS),
        "analysis",
        "click",
        shortcut="C",
    ),
    _WidgetAction(
        "image_compare.quick_save",
        "btn_quick_save",
        "image_compare.action.quick_save",
        "tooltip.quick_save_image",
        (_BC_TOOLBAR, _BC_EXPORT),
        "export",
        "click",
        shortcut="Ctrl+S",
    ),
    _WidgetAction(
        "image_compare.save",
        "btn_save",
        "image_compare.action.save",
        "tooltip.save_result",
        (_BC_TOOLBAR, _BC_EXPORT),
        "export",
        "click",
        shortcut=None,
    ),
    _WidgetAction(
        "image_compare.record",
        "btn_record",
        "image_compare.action.record",
        "tooltip.record_video",
        (_BC_TOOLBAR, _BC_VIDEO),
        "video",
        "click",
        shortcut="R",
    ),
    _WidgetAction(
        "image_compare.pause_recording",
        "btn_pause",
        "image_compare.action.pause_recording",
        "tooltip.pause_recording",
        (_BC_TOOLBAR, _BC_VIDEO),
        "video",
        "click",
    ),
    _WidgetAction(
        "image_compare.video_editor",
        "btn_video_editor",
        "image_compare.action.video_editor",
        "tooltip.open_video_editor",
        (_BC_TOOLBAR, _BC_VIDEO),
        "video",
        "click",
        shortcut="Ctrl+E",
    ),
)

_DIFF_OPTION_SPECS: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    ("off", "image_compare.action.diff_off", "off", ("off",)),
    ("highlight", "image_compare.action.diff_highlight", "highlight", ("highlight",)),
    ("grayscale", "image_compare.action.diff_grayscale", "grayscale", ("grayscale",)),
    ("edges", "image_compare.action.diff_edges", "edges", ("edges",)),
    ("ssim", "image_compare.action.diff_ssim", "ssim", ("ssim",)),
)

_CHANNEL_OPTION_SPECS: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    ("rgb", "image_compare.action.channel_rgb", "RGB", ("rgb",)),
    ("red", "image_compare.action.channel_red", "R", ("red", "r")),
    ("green", "image_compare.action.channel_green", "G", ("green", "g")),
    ("blue", "image_compare.action.channel_blue", "B", ("blue", "b")),
    ("luminance", "image_compare.action.channel_luminance", "L", ("luminance", "luma")),
)

_INTERP_OPTION_SPECS: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    ("nearest", "magnifier.nearest_neighbor", "NEAREST", ("nearest", "nn")),
    ("bilinear", "magnifier.bilinear", "BILINEAR", ("bilinear",)),
    ("bicubic", "magnifier.bicubic", "BICUBIC", ("bicubic",)),
    ("lanczos", "magnifier.lanczos", "LANCZOS", ("lanczos",)),
    ("ewa_lanczos", "magnifier.ewa_lanczos", "EWA_LANCZOS", ("ewa", "ewa_lanczos")),
)

_NAME_EDIT_SPECS: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    (
        "image_compare.rename_image1",
        "edit_name1",
        "image_compare.ui.edit_current_image_1_name",
        ("rename", "name1", "image1"),
    ),
    (
        "image_compare.rename_image2",
        "edit_name2",
        "image_compare.ui.edit_current_image_2_name",
        ("rename", "name2", "image2"),
    ),
)

_MAGNIFIER_SLIDER_SPECS: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    (
        "image_compare.magnifier.slider_size",
        "slider_size",
        "image_compare.label.magnifier_size",
        ("magnifier size", "zoom"),
    ),
    (
        "image_compare.magnifier.slider_capture",
        "slider_capture",
        "image_compare.label.capture_size",
        ("capture size",),
    ),
    (
        "image_compare.magnifier.slider_speed",
        "slider_speed",
        "magnifier.move_speed",
        ("movement speed", "speed"),
    ),
)

_MAGNIFIER_VISIBILITY_SLOTS: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    ("left", "btn_left", "image_compare.action.magnifier_visibility_left", ("left",)),
    (
        "center",
        "btn_center",
        "image_compare.action.magnifier_visibility_center",
        ("center", "combined"),
    ),
    (
        "right",
        "btn_right",
        "image_compare.action.magnifier_visibility_right",
        ("right",),
    ),
)

_MAGNIFIER_COLOR_OPTION_SPECS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("capture", "image_compare.magnifier.capture_ring", ("capture", "capture ring")),
    ("laser", "image_compare.label.guides", ("laser", "guides")),
    ("border", "image_compare.label.border", ("border",)),
    (
        "divider",
        "image_compare.ui.choose_magnifier_divider_line_color",
        ("divider", "split line"),
    ),
)

_MAGNIFIER_COLOR_BUTTON_ATTRS: tuple[str, ...] = (
    "btn_magnifier_color_settings",
    "btn_magnifier_color_settings_beginner",
)
