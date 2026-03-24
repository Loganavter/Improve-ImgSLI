import logging

from plugins.settings.presenter import SettingsPresenter
from resources.translations import tr
from shared_toolkit.ui.icon_manager import AppIcon

logger = logging.getLogger("ImproveImgSLI")

def show_divider_color_picker(presenter):
    settings_presenter = _get_settings_presenter_from_window(presenter)
    if settings_presenter:
        settings_presenter.show_divider_color_picker()
    else:
        logger.warning("ToolbarPresenter: settings_presenter not found")

def show_magnifier_divider_color_picker(presenter):
    settings_presenter = _get_settings_presenter_from_window(presenter)
    if settings_presenter:
        settings_presenter.show_magnifier_divider_color_picker()
    else:
        logger.warning("ToolbarPresenter: settings_presenter not found")

def check_name_lengths(presenter):
    len1 = len(presenter.ui.edit_name1.text().strip())
    len2 = len(presenter.ui.edit_name2.text().strip())
    limit = presenter.store.viewport.max_name_length
    if (
        len1 > limit or len2 > limit
    ) and presenter.store.viewport.include_file_names_in_saved:
        warning = tr(
            "Name length limit ({limit}) exceeded!",
            presenter.store.settings.current_language,
        ).format(limit=limit)
        presenter.ui.update_name_length_warning(warning, "", True)
    else:
        presenter.ui.update_name_length_warning("", "", False)

def update_toolbar_states(presenter):
    presenter.ui.btn_orientation.setChecked(
        presenter.store.viewport.is_horizontal, emit_signal=False
    )
    presenter.ui.btn_magnifier_orientation.setChecked(
        presenter.store.viewport.magnifier_is_horizontal, emit_signal=False
    )
    presenter.ui.btn_magnifier.setChecked(
        presenter.store.viewport.use_magnifier, emit_signal=False
    )
    presenter.ui.btn_freeze.setChecked(
        presenter.store.viewport.freeze_magnifier, emit_signal=False
    )
    presenter.ui.btn_file_names.setChecked(
        presenter.store.viewport.include_file_names_in_saved, emit_signal=False
    )
    image_label = getattr(presenter.ui, "image_label", None)
    zoom_level = float(getattr(image_label, "zoom_level", 1.0)) if image_label is not None else 1.0
    file_names_temporarily_hidden = (
        presenter.store.viewport.include_file_names_in_saved and abs(zoom_level - 1.0) > 1e-6
    )
    if hasattr(presenter.ui.btn_file_names, "setVisualIconOverride"):
        presenter.ui.btn_file_names.setVisualIconOverride(
            AppIcon.DIVIDER_HIDDEN if file_names_temporarily_hidden else None
        )
    lang = presenter.store.settings.current_language
    presenter.ui.btn_file_names.setToolTip(
        tr("tooltip.file_names_hidden_while_zoomed", lang)
        if file_names_temporarily_hidden
        else tr("ui.include_file_names_in_saved_image", lang)
    )

    divider_thickness = (
        0
        if not presenter.store.viewport.divider_line_visible
        else presenter.store.viewport.divider_line_thickness
    )
    magnifier_thickness = (
        0
        if not presenter.store.viewport.magnifier_divider_visible
        else presenter.store.viewport.magnifier_divider_thickness
    )

    presenter.ui.btn_orientation.set_value(divider_thickness)
    presenter.ui.btn_magnifier_orientation.set_value(magnifier_thickness)
    presenter.ui.slider_size.setValue(
        int(presenter.store.viewport.magnifier_size_relative * 100)
    )
    presenter.ui.slider_capture.setValue(
        int(presenter.store.viewport.capture_size_relative * 100)
    )
    presenter.ui.slider_speed.setValue(
        int(presenter.store.viewport.movement_speed_per_sec * 10)
    )

def on_color_option_clicked(presenter, option: str):
    settings_presenter = None
    if hasattr(presenter.main_controller, "settings_ctrl") and hasattr(
        presenter.main_controller.settings_ctrl, "presenter"
    ):
        settings_presenter = presenter.main_controller.settings_ctrl.presenter

    if not settings_presenter:
        settings_presenter = SettingsPresenter(
            presenter.store,
            presenter.main_controller,
            presenter.ui_manager,
            presenter.main_window_app,
        )

    if option == "divider":
        settings_presenter.show_magnifier_divider_color_picker()
    elif option == "capture":
        settings_presenter.show_capture_ring_color_picker()
    elif option == "border":
        settings_presenter.show_magnifier_border_color_picker()
    elif option == "laser":
        settings_presenter.show_laser_color_picker()

def _get_settings_presenter_from_window(presenter):
    if hasattr(presenter.main_window_app, "presenter") and hasattr(
        presenter.main_window_app.presenter, "settings_presenter"
    ):
        return presenter.main_window_app.presenter.settings_presenter
    return None
