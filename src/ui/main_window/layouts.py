from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QVBoxLayout,
    QWidget,
)

SHOW_WORKSPACE_TABS = False


def apply_workspace_tabs_visibility(ui) -> None:
    """Sync workspace-tabs row visibility with current store.settings.

    Safe to call before or after the store is attached: falls back to
    SHOW_WORKSPACE_TABS when no settings are available yet.
    """
    main_window = getattr(ui, "main_window", None)
    settings = getattr(getattr(main_window, "store", None), "settings", None)
    show = (
        getattr(settings, "show_workspace_tabs", SHOW_WORKSPACE_TABS)
        if settings is not None
        else SHOW_WORKSPACE_TABS
    )
    tabs = getattr(ui, "workspace_tabs", None)
    if tabs is not None:
        tabs.setVisible(show)
    btn = getattr(ui, "btn_new_session", None)
    if btn is not None:
        btn.setVisible(show)
    container = getattr(ui, "workspace_tabs_bar", None)
    if container is not None:
        container.setVisible(show)


class LayoutComposer:
    """Builds the main window layout tree.

    The host owns the workspace bar, the QStackedWidget and the video page.
    Tab pages are delegated to registered tab contracts. Some legacy tabs still
    assemble host-created primitive widgets through transitional hooks.
    """

    def __init__(self, ui):
        self.ui = ui

    def build(self, main_window: QWidget) -> None:
        main_layout = QVBoxLayout(main_window)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        main_layout.addWidget(self._workspace_bar_widget(main_window))
        self._configure_session_pages()

        ui = self.ui
        ui._tab_registry.assemble_host_pages(ui)

        main_layout.addWidget(self._workspace_content_widget(main_window), 1)

        self._finalize()

    def _finalize(self) -> None:
        ui = self.ui
        ui._tab_registry.finalize_host_pages(ui)
        active = getattr(getattr(ui.main_window, "store", None), "get_active_workspace_session", lambda: None)()
        if active is not None:
            ui.sync_session_mode(active.session_type)
        self._configure_workspace_tabs()

    def _configure_workspace_tabs(self) -> None:
        ui = self.ui
        tabs = ui.workspace_tabs
        tabs.setObjectName("WorkspaceTabsBar")
        tabs.tab_bar.setObjectName("WorkspaceTabs")
        apply_workspace_tabs_visibility(ui)

    def _workspace_bar_widget(self, main_window: QWidget) -> QWidget:
        ui = self.ui
        ui.workspace_tabs.setParent(main_window)
        ui.workspace_tabs.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        ui.workspace_tabs_bar = ui.workspace_tabs
        return ui.workspace_tabs

    def _workspace_content_widget(self, main_window: QWidget) -> QWidget:
        ui = self.ui
        container = QWidget(main_window)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(ui.workspace_stack)
        ui.workspace_content_widget = container
        return container

    def _configure_session_pages(self) -> None:
        self._install_tab_registry()

    def _install_tab_registry(self) -> None:
        from tabs.contract import TabContext
        from tabs.registry import TabRegistry

        ui = self.ui

        def _presenter():
            presenter = getattr(ui.main_window, "presenter", None)
            if presenter is None:
                raise RuntimeError("Main-window presenter is not initialized")
            return presenter

        def list_session_blueprints():
            return _presenter().main_controller.workspace.list_session_blueprints()

        def create_workspace_session(session_type: str, activate: bool = True):
            return _presenter().main_controller.workspace.create_workspace_session(
                session_type,
                activate=activate,
            )

        def close_workspace_session(session_id: str):
            return _presenter().main_controller.workspace.close_workspace_session(
                session_id
            )

        def _ui_manager():
            presenter = getattr(ui.main_window, "presenter", None)
            return (
                getattr(presenter, "ui_manager", None)
                if presenter is not None
                else None
            )

        def show_help_dialog(*, page: str | None = None, anchor: str | None = None):
            mgr = _ui_manager()
            if mgr is not None:
                mgr.dialogs.show_help_dialog(page=page, anchor=anchor)

        def show_settings_dialog(*, section_id: str | None = None):
            mgr = _ui_manager()
            if mgr is not None:
                mgr.dialogs.show_settings_dialog(section_id=section_id)

        def show_command_palette(
            query: str = "",
            topic: str | None = None,
            preselect_action_id: str | None = None,
            auto_pulse: bool = False,
        ):
            from ui.actions.palette import show_command_palette as _show

            parent = ui.main_window.window()
            _show(
                query=query,
                topic=topic,
                preselect_action_id=preselect_action_id,
                auto_pulse=auto_pulse,
                parent=parent,
            )

        def open_image_export_dialog(*, dialog_state, **kwargs):
            from PySide6.QtWidgets import QDialog

            from plugins.export.models import ExportDialogState

            mgr = _ui_manager()
            if mgr is None:
                return QDialog.DialogCode.Rejected, {}
            return mgr.dialogs.show_export_dialog(
                ExportDialogState(**dialog_state), **kwargs
            )

        from ui.main_window.workspace_transition_mask import (
            WorkspaceTransitionMask,
        )

        ui._tab_registry = TabRegistry()
        ui._tab_registry.discover(tier="bootstrap")
        transition_mask = WorkspaceTransitionMask(ui.main_window)
        ui.main_window._workspace_transition_mask = transition_mask
        # `ui.main_window` is set inside `Ui_ImageComparisonApp.setupUi()` to the
        # widget passed in (`window._app_host`, a plain QWidget), *before* the
        # caller overwrites it with the real MainWindow instance. So at this point
        # in startup, `ui.main_window` is still the app_host stand-in and lacks
        # `main_controller`/`app_context`/`thread_pool`. Walk up to the real
        # top-level window instead of trusting `ui.main_window` here.
        real_window = ui.main_window.window()
        store = getattr(ui.main_window, "store", None)
        main_controller = getattr(real_window, "main_controller", None)
        app_context = getattr(real_window, "app_context", None)
        event_bus = getattr(main_controller, "event_bus", None) or getattr(
            app_context, "event_bus", None
        )
        thread_pool = getattr(main_controller, "thread_pool", None) or getattr(
            app_context, "thread_pool", None
        )
        def get_tab_icon(session_type: str):
            from PySide6.QtGui import QIcon

            tab = ui._tab_registry.get_tab(session_type)
            if tab is None:
                return QIcon()
            icon = tab.icon
            return icon if icon is not None else QIcon()

        context = TabContext(
            store=store,
            event_bus=event_bus,
            thread_pool=thread_pool,
            main_window=real_window,
            settings=getattr(store, "settings", None),
            services={
                "list_session_blueprints": list_session_blueprints,
                "create_workspace_session": create_workspace_session,
                "close_workspace_session": close_workspace_session,
                "show_help_dialog": show_help_dialog,
                "show_settings_dialog": show_settings_dialog,
                "show_command_palette": show_command_palette,
                "open_image_export_dialog": open_image_export_dialog,
                "get_tab_icon": get_tab_icon,
                "workspace.transition_mask": transition_mask,
            },
        )
        ui._tab_registry.install_pages(ui.workspace_stack, context)
        # The main-window shell (composer.py's "image_canvas" feature, etc.)
        # is built before any workspace session exists to activate via
        # `sync_session_mode()`. Seed whichever registered tab declares
        # itself the bootstrap default (see `TabContract.is_bootstrap_default`)
        # so `create_service`/`create_main_window_feature` — which resolve
        # *only* against the active tab, see docs/dev/tabs/capability-mechanisms.md —
        # have someone to route to during this bootstrap window. The first
        # real `sync_session_mode()` call reconciles this with the actual
        # initial session's type. Deliberately tab-name-agnostic: this file
        # must not know which tab that is.
        ui._tab_registry.activate_default()

        if event_bus is not None:
            from core.events import (
                WorkspaceSessionActivatedEvent,
                WorkspaceSessionClosedEvent,
                WorkspaceSessionCreatedEvent,
            )

            event_bus.subscribe(
                WorkspaceSessionCreatedEvent,
                lambda e: ui._tab_registry.notify_session_created(
                    e.session_type, e.session_id
                ),
            )
            event_bus.subscribe(
                WorkspaceSessionClosedEvent,
                lambda e: ui._tab_registry.notify_session_closed(
                    e.session_type, e.session_id
                ),
            )
            event_bus.subscribe(
                WorkspaceSessionActivatedEvent,
                lambda e: ui._tab_registry.notify_active_session_changed(
                    e.session_id,
                    e.session_type,
                    e.previous_session_id,
                ),
            )
            dispatcher = getattr(store, "get_dispatcher", lambda: None)()
            if dispatcher is not None:
                event_bus.subscribe(
                    WorkspaceSessionActivatedEvent,
                    lambda e: dispatcher.bind_history_for_session(e.session_id),
                )
                active = store.get_active_workspace_session()
                if active is not None:
                    dispatcher.bind_history_for_session(active.id)
