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

        # Pin the session object across the dialog defer: the lambda runs up
        # to 100ms later, by which time main_controller.sessions may have
        # been rebound (tab switch / session rebuild) — loading into the
        # live attribute then would target the wrong session or crash on
        # None. The pinned ref always targets the session that owned the
        # dialog; a dead session is a guarded no-op via load_images...
        # failure paths, never a misdirected load.
        main_controller = presenter.main_controller
        sessions = (
            getattr(main_controller, "sessions", None)
            if main_controller is not None
            else None
        )
        pinned_paths = list(paths)

        QTimer.singleShot(
            delay,
            lambda: (
                sessions.load_images_from_paths(pinned_paths, image_number)
                if sessions is not None
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
    dispatcher = presenter.store.get_dispatcher()
    if dispatcher is not None:
        import importlib

        _magnifier_actions = importlib.import_module(
            "tabs.image_compare.canvas.features.magnifier.input.actions"
        )
        SetHighlightedMagnifierElementAction = _magnifier_actions.SetHighlightedMagnifierElementAction

        dispatcher.dispatch(SetHighlightedMagnifierElementAction(element_name), scope="viewport")
    if presenter.event_bus:
        presenter.event_bus.emit(CoreUpdateRequestedEvent())
    else:
        presenter.main_controller.update_requested.emit()

def on_magnifier_element_hover_ended(presenter):
    if not presenter.store:
        return
    dispatcher = presenter.store.get_dispatcher()
    if dispatcher is not None:
        import importlib

        _magnifier_actions = importlib.import_module(
            "tabs.image_compare.canvas.features.magnifier.input.actions"
        )
        SetHighlightedMagnifierElementAction = _magnifier_actions.SetHighlightedMagnifierElementAction

        dispatcher.dispatch(SetHighlightedMagnifierElementAction(None), scope="viewport")
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
