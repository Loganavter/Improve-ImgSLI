from __future__ import annotations

from dataclasses import dataclass

from plugins.export.presenter import ExportPresenter
from plugins.settings.presenter import SettingsPresenter
from ui.managers.ui_manager import UIManager
from ui.presenters.image_canvas.presenter import ImageCanvasPresenter
from ui.presenters.toolbar_presenter import ToolbarPresenter

@dataclass(slots=True)
class MainWindowFeatureSet:
    ui_manager: UIManager
    image_canvas: ImageCanvasPresenter
    toolbar: ToolbarPresenter
    export: ExportPresenter
    settings: SettingsPresenter

def build_main_window_features(
    *,
    store,
    main_controller,
    ui,
    main_window_app,
    plugin_ui_registry=None,
) -> MainWindowFeatureSet:
    ui_manager = UIManager(
        store,
        main_controller,
        ui,
        main_window_app,
        plugin_ui_registry=plugin_ui_registry,
    )
    image_canvas = ImageCanvasPresenter(store, main_controller, ui, main_window_app)
    toolbar = ToolbarPresenter(
        store,
        main_controller,
        ui,
        main_window_app,
        ui_manager=ui_manager,
    )
    export = ExportPresenter(
        store,
        main_controller,
        ui_manager,
        main_window_app,
        main_window_app.font_path_absolute,
        resource_manager=getattr(main_window_app, "ui_resource_manager", None),
    )
    settings = SettingsPresenter(
        store,
        main_controller,
        ui_manager,
        main_window_app,
    )
    return MainWindowFeatureSet(
        ui_manager=ui_manager,
        image_canvas=image_canvas,
        toolbar=toolbar,
        export=export,
        settings=settings,
    )
