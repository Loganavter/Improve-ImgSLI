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
        ui.toggle_edit_layout_visibility(False)
        ui.magnifier_settings_panel.setVisible(False)
        active = getattr(getattr(ui.main_window, "store", None), "get_active_workspace_session", lambda: None)()
        if active is not None:
            ui.sync_session_mode(active.session_type)
        self.apply_icon_sizes()
        self._configure_workspace_tabs()

    def apply_icon_sizes(self) -> None:
        ui = self.ui
        ui.btn_quick_save.setIconSizePx(24)
        ui.help_button.setIconSizePx(24)
        ui.btn_clear_list1.setIconSizePx(22)
        ui.btn_clear_list2.setIconSizePx(22)
        ui.btn_divider_color.setIconSizePx(22)
        ui.btn_divider_width.setIconSizePx(22)
        ui.btn_magnifier_divider_width.setIconSizePx(22)
        ui.btn_magnifier_guides_width.setIconSizePx(22)

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

        def show_help_dialog():
            mgr = _ui_manager()
            if mgr is not None:
                mgr.dialogs.show_help_dialog()

        def show_settings_dialog():
            mgr = _ui_manager()
            if mgr is not None:
                mgr.dialogs.show_settings_dialog()

        from ui.main_window.workspace_transition_mask import (
            WorkspaceTransitionMask,
        )

        ui._tab_registry = TabRegistry()
        ui._tab_registry.discover()
        transition_mask = WorkspaceTransitionMask(ui.main_window)
        ui.main_window._workspace_transition_mask = transition_mask
        store = getattr(ui.main_window, "store", None)
        main_controller = getattr(ui.main_window, "main_controller", None)
        app_context = getattr(ui.main_window, "app_context", None)
        event_bus = getattr(main_controller, "event_bus", None) or getattr(
            app_context, "event_bus", None
        )
        thread_pool = getattr(main_controller, "thread_pool", None) or getattr(
            app_context, "thread_pool", None
        )
        context = TabContext(
            store=store,
            event_bus=event_bus,
            thread_pool=thread_pool,
            main_window=ui.main_window,
            settings=getattr(store, "settings", None),
            services={
                "list_session_blueprints": list_session_blueprints,
                "create_workspace_session": create_workspace_session,
                "close_workspace_session": close_workspace_session,
                "show_help_dialog": show_help_dialog,
                "show_settings_dialog": show_settings_dialog,
                "workspace.transition_mask": transition_mask,
            },
        )
        ui._tab_registry.install_pages(ui.workspace_stack, context)
