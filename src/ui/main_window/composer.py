from __future__ import annotations

from dataclasses import dataclass
import os

from PySide6.QtWidgets import QApplication

from core.main_controller import MainController
from events.app_event_handler import EventHandler
from shared_toolkit.ui.managers.ui_resource_manager import UIResourceManager
from ui.managers.tray_manager import TrayManager
from ui.presenters.main_window.features import build_main_window_features
from ui.presenters.main_window.presenter import MainWindowPresenter
from utils.geometry import GeometryManager

@dataclass(slots=True)
class MainWindowComponents:
    geometry_manager: GeometryManager
    tray_manager: TrayManager | None
    main_controller: MainController
    event_handler: EventHandler
    presenter: MainWindowPresenter
    ui_resource_manager: UIResourceManager

class MainWindowComposer:
    def __init__(self, context):
        self.context = context

    def _should_enable_system_tray(self) -> bool:
        override = os.environ.get("IMPROVE_ENABLE_TRAY")
        if override is not None:
            return override == "1"
        return True

    def compose(self, window) -> MainWindowComponents:
        geometry_manager = GeometryManager(
            window,
            self.context.settings_manager.settings,
            self.context.store,
        )
        ui_resource_manager = UIResourceManager(window)
        window.ui_resource_manager = ui_resource_manager

        from events.drag_drop_handler import DragAndDropService

        if DragAndDropService._instance is None:
            DragAndDropService._instance = DragAndDropService(self.context.store, window)

        tray_manager = None
        if self._should_enable_system_tray():
            tray_manager = TrayManager(
                window,
                current_language=self.context.store.settings.current_language,
                resource_manager=ui_resource_manager,
            )
            tray_manager.toggle_visibility_requested.connect(
                window.actions.toggle_main_window_visibility
            )
            tray_manager.open_last_file_requested.connect(
                window.actions.open_last_saved_file
            )
            tray_manager.open_last_folder_requested.connect(
                window.actions.open_last_saved_folder
            )
            tray_manager.quit_requested.connect(QApplication.instance().quit)

        main_controller = MainController(self.context)
        event_handler = EventHandler(self.context.store, None)
        features = build_main_window_features(
            store=self.context.store,
            main_controller=main_controller,
            ui=window.ui,
            main_window_app=window,
            plugin_ui_registry=self.context.plugin_ui_registry,
        )
        presenter = MainWindowPresenter(
            window,
            window.ui,
            self.context.store,
            main_controller,
            features=features,
            plugin_ui_registry=self.context.plugin_ui_registry,
        )
        event_handler.presenter = presenter
        main_controller.attach_window_shell(presenter)
        presenter.connect_event_handler_signals(event_handler)

        self.context.notification_service.set_tray_icon(
            tray_manager.tray_icon if tray_manager is not None else None
        )

        return MainWindowComponents(
            geometry_manager=geometry_manager,
            tray_manager=tray_manager,
            main_controller=main_controller,
            event_handler=event_handler,
            presenter=presenter,
            ui_resource_manager=ui_resource_manager,
        )
