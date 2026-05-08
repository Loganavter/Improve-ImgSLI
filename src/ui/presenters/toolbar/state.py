import logging
from PyQt6.QtCore import QSignalBlocker
from resources.translations import tr
from shared_toolkit.ui.icon_manager import AppIcon
from ui.canvas_features.magnifier import MagnifierModeService, MagnifierStoreService
from ui.canvas_features.magnifier.store import (
    active_or_default_divider_thickness,
    active_or_default_divider_visible,
    default_capture_size,
    default_magnifier_size,
)
from ui.canvas_infra.scene.widget_registry import get_canvas_feature_toolbar_bindings
from ui.canvas_infra.viewport.state import get_zoom_level

logger = logging.getLogger("ImproveImgSLI")

def _set_slider_value_quietly(slider, value: int) -> None:
    if slider.value() == value:
        return
    blocker = QSignalBlocker(slider)
    try:
        slider.setValue(value)
    finally:
        del blocker

def show_magnifier_divider_color_picker(presenter):
    settings_presenter = _get_settings_presenter_from_window(presenter)
    if settings_presenter:
        settings_presenter.show_magnifier_divider_color_picker()
    else:
        logger.warning("ToolbarPresenter: settings_presenter not found")

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

def update_toolbar_states(presenter):
    scene_state = MagnifierStoreService(presenter.store)
    mode_service = MagnifierModeService(presenter.store)
    active_magnifier = scene_state.get_active_or_first_magnifier()
    magnifier_is_horizontal = bool(active_magnifier.is_horizontal) if active_magnifier is not None else False
    magnifier_size = (
        float(active_magnifier.size_relative)
        if active_magnifier is not None
        else float(default_magnifier_size(presenter.store.viewport.view_state))
    )
    capture_size = (
        float(active_magnifier.capture_size_relative)
        if active_magnifier is not None
        else float(default_capture_size(presenter.store.viewport.view_state))
    )
    presenter.ui.btn_magnifier_orientation.setChecked(
        magnifier_is_horizontal, emit_signal=False
    )
    presenter.ui.btn_magnifier.setChecked(
        mode_service.resolve_button_checked(active_magnifier), emit_signal=False
    )
    if hasattr(presenter.ui, "btn_magnifier_instances"):
        count = len(scene_state.iter_magnifiers())
        presenter.ui.btn_magnifier_instances.set_magnifier_count(count if count > 0 else 1)
        presenter.ui.btn_magnifier_instances.set_can_remove(count > 1)
    presenter.ui.btn_freeze.setChecked(
        scene_state.are_all_magnifiers_frozen(), emit_signal=False
    )
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

    magnifier_thickness = (
        0
        if not active_or_default_divider_visible(presenter.store.viewport.view_state)
        else active_or_default_divider_thickness(presenter.store.viewport.view_state)
    )
    presenter.ui.btn_magnifier_orientation.set_value(magnifier_thickness)
    _set_slider_value_quietly(
        presenter.ui.slider_size,
        int(magnifier_size * 100),
    )
    _set_slider_value_quietly(
        presenter.ui.slider_capture,
        int(capture_size * 100),
    )
    _set_slider_value_quietly(
        presenter.ui.slider_speed,
        int(presenter.store.viewport.view_state.movement_speed_per_sec * 10),
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
