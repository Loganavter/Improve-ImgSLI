from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from plugins.settings.presenter import SettingsPresenter
from ui.managers.ui_manager import UIManager


class _LazyTabService:
    """Lazily resolve a tab-owned service via the registry.

    The service is not created until first access — tab-specific services
    (toolbar, export) are only needed when their tab is active, not at
    startup.  ``None`` is never cached so re-probe happens when the tab's
    page is materialized.
    """

    def __init__(self, service_id: str, *args, **kwargs):
        self._service_id = service_id
        self._args = args
        self._kwargs = kwargs
        self._resolved: Any = _UNSET
        self._tried: bool = False

    def _resolve(self):
        if self._resolved is not _UNSET:
            return self._resolved
        from tabs.registry import TabRegistry

        registry = TabRegistry()
        registry.discover()
        service = registry.create_startup_service(
            self._service_id, *self._args, **self._kwargs
        )
        if service is not None:
            self._resolved = service
            self._tried = True
        return self._resolved if self._tried else None

    def __getattr__(self, name: str):
        resolved = self._resolve()
        if resolved is None:
            raise AttributeError(
                f"Tab service '{self._service_id}' not available yet "
                f"(tab page not materialized)"
            )
        return getattr(resolved, name)


_UNSET = object()


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
    toolbar = _LazyTabService(
        "toolbar_presenter",
        store,
        main_controller,
        ui,
        main_window_app,
        ui_manager,
    )
    export = _LazyTabService(
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
