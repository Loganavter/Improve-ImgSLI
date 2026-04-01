from __future__ import annotations

import logging
import time

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from core.events import ViewportToggleMagnifierPartEvent
from shared_toolkit.ui.managers.flyout_timer_service import DelayedActionTimer
from shared_toolkit.ui.managers.font_manager import FontManager

logger = logging.getLogger("ImproveImgSLI")

def initialize_ui_manager(manager) -> None:
    _init_unified_flyout(manager)
    _init_popup_state(manager)
    _wrap_button_menus(manager)
    _init_magnifier_flyout(manager)
    _connect_services(manager)

def _init_unified_flyout(manager) -> None:
    from shared_toolkit.ui.widgets.composite.unified_flyout import UnifiedFlyout

    manager.unified_flyout = UnifiedFlyout(
        manager.store, manager.main_controller, manager.parent_widget
    )
    if manager.unified_flyout is not None:
        manager.unified_flyout.closing_animation_finished.connect(
            manager._on_unified_flyout_closed
        )

def _init_popup_state(manager) -> None:
    manager.font_settings_flyout = None
    manager._font_anchor_widget = None
    manager._is_modal_active = False

    manager._help_dialog = None
    manager._settings_dialog = None

    manager._interp_flyout = None
    manager._interp_popup_open = False
    manager._interp_last_open_ts = 0.0

    manager._font_popup_open = False
    manager._font_popup_last_open_ts = 0.0

    manager._diff_mode_popup_open = False
    manager._diff_mode_last_open_ts = 0.0
    manager._channel_mode_popup_open = False
    manager._channel_mode_last_open_ts = 0.0

    manager._magn_popup_open = False
    manager._magn_popup_last_open_ts = 0.0

def _wrap_button_menus(manager) -> None:
    ui = manager.ui
    if ui is None:
        return

    _install_menu_tracker(
        manager,
        button_name="btn_diff_mode",
        original_attr="_original_diff_show_menu",
        open_attr="_diff_mode_popup_open",
        opened_at_attr="_diff_mode_last_open_ts",
    )
    _install_menu_tracker(
        manager,
        button_name="btn_channel_mode",
        original_attr="_original_channel_show_menu",
        open_attr="_channel_mode_popup_open",
        opened_at_attr="_channel_mode_last_open_ts",
    )

def _install_menu_tracker(
    manager,
    *,
    button_name: str,
    original_attr: str,
    open_attr: str,
    opened_at_attr: str,
) -> None:
    button = getattr(manager.ui, button_name, None)
    if button is None:
        return

    try:
        original_show_menu = button.show_menu
    except AttributeError as exc:
        logger.warning(
            "UIManager bootstrap: %s.show_menu not available: %s",
            button_name,
            exc,
        )
        return

    setattr(manager, original_attr, original_show_menu)

    def wrapped_show_menu():
        result = original_show_menu()
        if hasattr(button, "_menu_visible") and button._menu_visible:
            setattr(manager, open_attr, True)
            setattr(manager, opened_at_attr, time.monotonic())
        return result

    button.show_menu = wrapped_show_menu

def _init_magnifier_flyout(manager) -> None:
    from shared_toolkit.ui.widgets.composite.magnifier_visibility_flyout import (
        MagnifierVisibilityFlyout,
    )

    manager.magnifier_visibility_flyout = MagnifierVisibilityFlyout(
        manager.parent_widget
    )
    manager._magn_hover_timer = DelayedActionTimer(
        lambda: manager._show_magnifier_visibility_flyout(reason="hover"),
        parent=manager,
    )

    btn_magnifier = getattr(manager.ui, "btn_magnifier", None)
    if btn_magnifier is None:
        return

    btn_magnifier.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
    btn_magnifier.installEventFilter(manager)
    manager.magnifier_visibility_flyout.installEventFilter(manager)
    manager.magnifier_visibility_flyout.btn_left.installEventFilter(manager)
    manager.magnifier_visibility_flyout.btn_center.installEventFilter(manager)
    manager.magnifier_visibility_flyout.btn_right.installEventFilter(manager)
    btn_magnifier.toggled.connect(manager._on_magnifier_toggle_with_hover)

    _connect_magnifier_visibility_buttons(manager)

def _connect_magnifier_visibility_buttons(manager) -> None:
    if manager.main_controller is None:
        return

    viewport_ctrl = getattr(manager.main_controller, "viewport_plugin", None)
    flyout = manager.magnifier_visibility_flyout

    if manager.event_bus is not None:
        flyout.btn_left.toggled.connect(
            lambda checked: manager.event_bus.emit(
                ViewportToggleMagnifierPartEvent("left", not checked)
            )
        )
        flyout.btn_right.toggled.connect(
            lambda checked: manager.event_bus.emit(
                ViewportToggleMagnifierPartEvent("right", not checked)
            )
        )
        flyout.btn_center.toggled.connect(
            lambda checked: manager.event_bus.emit(
                ViewportToggleMagnifierPartEvent("center", not checked)
            )
        )
        return

    if viewport_ctrl is not None and hasattr(viewport_ctrl, "toggle_magnifier_part"):
        flyout.btn_left.toggled.connect(
            lambda checked: viewport_ctrl.toggle_magnifier_part("left", not checked)
        )
        flyout.btn_right.toggled.connect(
            lambda checked: viewport_ctrl.toggle_magnifier_part("right", not checked)
        )
        flyout.btn_center.toggled.connect(
            lambda checked: viewport_ctrl.toggle_magnifier_part("center", not checked)
        )
        return

    logger.warning(
        "UIManager: Cannot connect magnifier visibility flyout buttons - no event_bus or viewport_plugin available"
    )

def _connect_services(manager) -> None:
    font_manager = FontManager.get_instance()
    if font_manager is not None:
        font_manager.font_changed.connect(manager._on_font_changed)

    app = QApplication.instance()
    if app is not None:
        app.focusChanged.connect(manager._on_app_focus_changed)
        app.installEventFilter(manager)
    if manager.parent_widget is not None:
        manager.parent_widget.installEventFilter(manager)
