import logging
from PySide6.QtCore import QSignalBlocker
from resources.translations import tr
from shared_toolkit.ui.icon_manager import AppIcon
from ui.canvas_infra.scene.widget_registry import (
    get_canvas_feature_toolbar_binding,
    get_canvas_feature_toolbar_bindings,
)
from ui.canvas_infra.viewport.state import get_zoom_level

logger = logging.getLogger("ImproveImgSLI")

_TOOLBAR_CONTROL_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("btn_orientation", ("divider.orientation",)),
    ("btn_orientation_simple", ("divider.orientation_simple",)),
    ("btn_divider_visible", ("divider.visible",)),
    ("btn_divider_color", ("divider.color",)),
    ("btn_divider_width", ("divider.width",)),
    ("btn_magnifier", ("magnifier.enabled",)),
    ("btn_magnifier_orientation", ("magnifier.orientation", "magnifier.divider.thickness")),
    ("btn_magnifier_orientation_simple", ("magnifier.orientation",)),
    ("btn_magnifier_divider_visible", ("magnifier.divider.visibility",)),
    ("btn_magnifier_divider_width", ("magnifier.divider.thickness",)),
    ("btn_magnifier_instances", ("magnifier.instances.add", "magnifier.instances.remove")),
    ("btn_freeze", ("magnifier.freeze",)),
    ("slider_size", ("magnifier.size",)),
    ("slider_capture", ("capture.size",)),
    ("btn_file_names", ("filename_overlay.visible",)),
    ("btn_magnifier_guides_simple", ("guides.enabled_simple",)),
    ("btn_magnifier_guides_width", ("guides.thickness",)),
)

def _set_slider_value_quietly(slider, value: int) -> None:
    if slider.value() == value:
        return
    blocker = QSignalBlocker(slider)
    try:
        slider.setValue(value)
    finally:
        del blocker

def check_name_lengths(presenter):
    len1 = len(presenter.ui.edit_name1.text().strip())
    len2 = len(presenter.ui.edit_name2.text().strip())
    limit = presenter.store.viewport.render_config.max_name_length
    if (
        len1 > limit or len2 > limit
    ) and presenter.store.viewport.render_config.include_file_names_in_saved:
        warning = tr(
            "misc.name_length_limit_exceeded",
            presenter.store.settings.current_language,
            limit=limit,
        )
        presenter.ui.update_name_length_warning(warning, "", True)
    else:
        presenter.ui.update_name_length_warning("", "", False)

def _update_canvas_feature_control_availability(presenter) -> None:
    ui = getattr(presenter, "ui", None)
    if ui is None:
        return
    for attr_name, control_ids in _TOOLBAR_CONTROL_GROUPS:
        widget = getattr(ui, attr_name, None)
        if widget is None or not hasattr(widget, "setEnabled"):
            continue
        widget.setEnabled(
            any(get_canvas_feature_toolbar_binding(control_id) is not None for control_id in control_ids)
        )

def update_toolbar_states(presenter):
    presenter.ui.btn_file_names.setChecked(
        presenter.store.viewport.render_config.include_file_names_in_saved, emit_signal=False
    )
    image_label = getattr(presenter.ui, "image_label", None)
    zoom_level = get_zoom_level(image_label) if image_label is not None else 1.0
    file_names_temporarily_hidden = (
        presenter.store.viewport.render_config.include_file_names_in_saved and abs(zoom_level - 1.0) > 1e-6
    )
    if hasattr(presenter.ui.btn_file_names, "setVisualIconOverride"):
        presenter.ui.btn_file_names.setVisualIconOverride(
            AppIcon.DIVIDER_HIDDEN if file_names_temporarily_hidden else None
        )
    lang = presenter.store.settings.current_language
    presenter.ui.btn_file_names.setToolTip(
        tr("tooltip.file_names_hidden_on_zoom", lang)
        if file_names_temporarily_hidden
        else tr("ui.include_file_names_in_saved_image", lang)
    )
    _update_canvas_feature_control_availability(presenter)
    _set_slider_value_quietly(
        presenter.ui.slider_speed,
        int(presenter.store.viewport.view_state.movement_speed_per_sec * 100),
    )
    for binding in get_canvas_feature_toolbar_bindings():
        if binding.sync_state is not None:
            binding.sync_state(presenter)

def on_color_option_clicked(presenter, option: str):
    settings_presenter = _get_settings_presenter_from_window(presenter)
    if settings_presenter is None:
        logger.warning("ToolbarPresenter: settings_presenter not found")
        return

    if option == "divider":
        settings_presenter.show_magnifier_divider_color_picker()
    elif option == "capture":
        settings_presenter.show_capture_ring_color_picker()
    elif option == "border":
        settings_presenter.show_magnifier_border_color_picker()
    elif option == "laser":
        settings_presenter.show_laser_color_picker()

def _get_settings_presenter_from_window(presenter):
    window_presenter = getattr(presenter.main_window_app, "presenter", None)
    if window_presenter is not None and hasattr(window_presenter, "get_feature"):
        return window_presenter.get_feature("settings")
    return None
