import os

from PySide6.QtWidgets import QFileDialog

from core.events import CoreUpdateRequestedEvent
from sli_ui_toolkit.i18n import tr
from tabs.image_compare.canvas.registry import registry
from tabs.image_compare.presenters.toolbar.state import _get_settings_presenter_from_window

def open_image_dialog(presenter, image_number: int):
    start_dir = presenter.store.settings.export_default_dir or os.path.expanduser("~")
    lang = presenter.store.settings.current_language
    filters = (
        f"{tr('common.file_type.image_files', lang)} "
        "(*.png *.bmp *.gif *.webp *.tif *.tiff *.jxl *.jpg *.jpeg);;"
        f"{tr('common.file_type.all_files', lang)} (*)"
    )
    paths, _ = QFileDialog.getOpenFileNames(
        presenter.main_window_app,
        tr("image_compare.button.select_images", lang),
        start_dir,
        filters,
    )

    if paths:
        delay = 100 if getattr(presenter, "_first_dialog_load_pending", True) else 0
        from PySide6.QtCore import QTimer

        QTimer.singleShot(
            delay,
            lambda: (
                presenter.main_controller.sessions.load_images_from_paths(
                    paths, image_number
                )
                if presenter.main_controller is not None
                and presenter.main_controller.sessions is not None
                else None
            ),
        )
        presenter._first_dialog_load_pending = False

def on_magnifier_guides_toggled(presenter, checked: bool):
    binding = registry().get_feature_toolbar_binding("guides.enabled")
    if binding is not None and binding.on_toggled is not None:
        binding.on_toggled(presenter, checked)

def on_magnifier_guides_thickness_changed(presenter, thickness: int):
    binding = registry().get_feature_toolbar_binding("guides.thickness")
    if binding is not None and binding.on_value_changed is not None:
        binding.on_value_changed(presenter, thickness)

def on_magnifier_element_hovered(presenter, element_name: str):
    if not presenter.store:
        return
    presenter.store.viewport.view_state.highlighted_overlay_element = element_name
    presenter.store.emit_state_change()
    if presenter.event_bus:
        presenter.event_bus.emit(CoreUpdateRequestedEvent())
    else:
        presenter.main_controller.update_requested.emit()

def on_magnifier_element_hover_ended(presenter):
    if not presenter.store:
        return
    presenter.store.viewport.view_state.highlighted_overlay_element = None
    presenter.store.emit_state_change()
    if presenter.event_bus:
        presenter.event_bus.emit(CoreUpdateRequestedEvent())
    else:
        presenter.main_controller.update_requested.emit()

def on_color_option_clicked(presenter, option: str):
    settings_presenter = _get_settings_presenter_from_window(presenter)
    if settings_presenter is None:
        return
    if option == "divider":
        settings_presenter.show_magnifier_divider_color_picker()
    elif option == "capture":
        settings_presenter.show_capture_ring_color_picker()
    elif option == "border":
        settings_presenter.show_magnifier_border_color_picker()
    elif option == "laser":
        settings_presenter.show_laser_color_picker()
