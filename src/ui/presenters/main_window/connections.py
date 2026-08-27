from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QWidget

from ui.presenters.main_window.actions import (
    on_error_occurred,
    on_ui_update_requested,
    on_update_requested,
)
from ui.presenters.main_window.state import on_store_state_changed
from ui.presenters.main_window.workspace import (
    on_new_workspace_tab_requested,
    on_workspace_tab_changed,
    on_workspace_tab_close_requested,
)
from ui.presenters.main_window.workspace_tab_menu import (
    on_workspace_tab_context_menu_requested,
)


def _focus_content(presenter, direction: int) -> None:
    """Focus the first interactive widget in the content area."""
    import logging
    _log = logging.getLogger(__name__)
    from PySide6.QtWidgets import QAbstractScrollArea, QStackedWidget

    stack = getattr(presenter.ui, "workspace_stack", None)
    if stack is None:
        return
    page = stack.currentWidget()
    if page is None:
        return
    for child in page.findChildren(QWidget):
        if isinstance(child, (QAbstractScrollArea, QStackedWidget)):
            continue
        if child.focusPolicy() in (
            Qt.FocusPolicy.StrongFocus,
            Qt.FocusPolicy.ClickFocus,
            Qt.FocusPolicy.WheelFocus,
        ):
            _log.debug(
                "[NAV] _focus_content: focusing %s", type(child).__name__
            )
            child.setFocus(Qt.FocusReason.OtherFocusReason)
            return
    _log.debug("[NAV] _focus_content: no focusable widget found")


def connect_signals(presenter):
    presenter.store.state_changed.connect(
        lambda domain: on_store_state_changed(presenter, domain)
    )

    presenter.main_controller.error_occurred.connect(
        lambda error_message: on_error_occurred(presenter, error_message)
    )
    presenter.main_controller.update_requested.connect(
        lambda: on_update_requested(presenter)
    )
    presenter.main_controller.ui_update_requested.connect(
        lambda components: on_ui_update_requested(presenter, components)
    )
    # `image_canvas` is resolved lazily (not materialized until its tab is
    # active) — defer attribute access to signal-fire time via lambda rather
    # than binding a method reference now, which would force resolution
    # (and likely raise) before the tab exists. Guard the call so the
    # generic resize-settle/startup-drain path (MainWindow.schedule_update
    # etc.) does not raise when session_picker is active — see
    # docs/dev/investigations/lazy-legacy-shell-plan.md open question 2.
    def _guarded_start():
        method = getattr(
            presenter.features.image_canvas, "start_interactive_movement", None
        )
        if method is not None:
            try:
                method()
            except AttributeError:
                pass

    def _guarded_stop():
        method = getattr(
            presenter.features.image_canvas, "stop_interactive_movement", None
        )
        if method is not None:
            try:
                method()
            except AttributeError:
                pass

    presenter.main_controller.start_interactive_movement.connect(_guarded_start)
    presenter.main_controller.stop_interactive_movement.connect(_guarded_stop)

    presenter.ui.workspace_tabs.currentChanged.connect(
        lambda index: on_workspace_tab_changed(presenter, index)
    )
    presenter.ui.workspace_tabs.tabCloseRequested.connect(
        lambda index: on_workspace_tab_close_requested(presenter, index)
    )
    presenter.ui.workspace_tabs.addRequested.connect(
        lambda: on_new_workspace_tab_requested(presenter)
    )
    presenter.ui.workspace_tabs.navigateOutRequested.connect(
        lambda direction: _focus_content(presenter, direction)
    )
    presenter.ui.workspace_tabs.tabContextMenuRequested.connect(
        lambda index, global_pos: on_workspace_tab_context_menu_requested(
            presenter, index, global_pos
        )
    )

    _refresh_active_tab_actions()


def _refresh_active_tab_actions() -> None:
    from tabs.registry import get_shared_tab_registry
    from ui.actions.binder import resync_action_shortcuts
    from ui.actions.registry import get_action_registry
    from ui.helpers.window_resolver import find_main_window

    get_shared_tab_registry().create_service(
        "contribute_actions",
        get_action_registry(),
    )
    window = QApplication.activeWindow()
    if window is None:
        window = find_main_window()
    resync_action_shortcuts(window)


def connect_event_handler_signals(presenter, event_handler):
    # image_canvas's own `connect_event_handler_signals(event_handler)` call
    # (not idempotent — must fire exactly once) is wired via the
    # `on_resolved` callback attached to its `LazyTabService` in
    # composer.py, since image_canvas may not be materialized yet here.
    event_handler.mouse_press_event_signal.connect(
        lambda event: handle_global_mouse_press(presenter, event)
    )
    presenter.main_controller.start_interactive_movement.connect(
        event_handler.start_interactive_movement
    )
    presenter.main_controller.stop_interactive_movement.connect(
        event_handler.stop_interactive_movement
    )


def repopulate_flyouts(presenter):
    if presenter.ui_manager:
        presenter.ui_manager.transient.repopulate_flyouts()


def _press_is_on_title_bar_menu(global_pos) -> bool:
    """True when the press targets a CSD File/Help menu trigger.

    Title-bar menus open on ``clicked`` (mouse *release*). The deferred
    outside-click closer scheduled from this press would otherwise run on the
    next event-loop tick and hide the menu that just opened — first click
    looks like a no-op (common with Image/Multi Compare flyout stacks).
    """
    try:
        point = global_pos.toPoint()
    except AttributeError:
        point = global_pos
    widget = QApplication.widgetAt(point)
    while widget is not None:
        name = widget.objectName()
        if name in {"CsdMenuTrigger", "CsdMenuStrip"}:
            return True
        parent = widget.parentWidget()
        if parent is not None and parent.objectName() in {
            "CsdMenuTrigger",
            "CsdMenuStrip",
        }:
            return True
        widget = parent
    return False


def handle_global_mouse_press(presenter, event):
    if event.button() == Qt.MouseButton.RightButton:
        return
    global_pos = event.globalPosition()
    if _press_is_on_title_bar_menu(global_pos):
        return

    # Coalesce bursts (duplicate filters / synthetic presses) into one close.
    if getattr(presenter, "_popup_close_scheduled", False):
        return
    presenter._popup_close_scheduled = True

    def _close_popups():
        presenter._popup_close_scheduled = False
        presenter.ui_manager.transient.close_all_flyouts_if_needed(global_pos)

    QTimer.singleShot(0, _close_popups)
