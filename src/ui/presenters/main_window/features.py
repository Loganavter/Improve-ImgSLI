from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from plugins.settings.presenter import SettingsPresenter
from ui.managers.ui_manager import UIManager

@dataclass(slots=True)
class MainWindowFeatureSet:
    ui_manager: UIManager
    image_canvas: Any
    toolbar: Any
    export: Any
    settings: SettingsPresenter

def build_main_window_features(
    *,
    store,
    main_controller,
    ui,
    main_window_app,
    image_canvas,
) -> MainWindowFeatureSet:
    ui_manager = UIManager(
        store,
        main_controller,
        ui,
        main_window_app,
    )
    from tabs.registry import TabRegistry

    registry = TabRegistry()
    registry.discover()
    toolbar = registry.create_startup_service(
        "toolbar_presenter",
        store,
        main_controller,
        ui,
        main_window_app,
        ui_manager,
    )
    # toolbar may be None with lazy tab initialization — the tab whose
    # page provides it hasn't been materialized yet.  It will be created
    # when that tab is first shown (see assemble_host_page / _ensure_page).
    export = registry.create_startup_service(
        "export_presenter",
        store,
        main_controller,
        ui_manager,
        main_window_app,
        main_window_app.font_path_absolute,
        resource_manager=getattr(main_window_app, "ui_resource_manager", None),
    )
    if export is None:
        raise RuntimeError("Tab export presenter service is unavailable")
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
