from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from plugins.settings.presenter import SettingsPresenter
from tabs.registry import LazyTabService
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
    # toolbar and export are tab-specific services — created lazily when
    # the owning tab's page is materialized, not at startup.
    toolbar = LazyTabService(
        "toolbar_presenter",
        store,
        main_controller,
        ui,
        main_window_app,
        ui_manager,
    )
    export = LazyTabService(
        "export_presenter",
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
