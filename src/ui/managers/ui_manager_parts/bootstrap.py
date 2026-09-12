from __future__ import annotations

import logging

from PySide6.QtWidgets import QApplication

from shared_toolkit.ui.managers.font_manager import FontManager

logger = logging.getLogger("ImproveImgSLI")

def initialize_ui_manager_pre_transient(manager) -> None:
    _init_unified_flyout(manager)
    _init_popup_state(manager)

def initialize_ui_manager_post_transient(manager) -> None:
    _connect_services(manager)

def _init_unified_flyout(manager) -> None:
    from ui.widgets.unified_list_picker import UnifiedListPicker

    from ui.widgets.rating_item import make_rating_row_factory

    manager.unified_flyout = UnifiedListPicker(
        manager.store, manager.main_controller, manager.parent_widget
    )
    flyout = manager.unified_flyout
    # The toolkit's flyout is a generic list picker; the rating row is
    # Improve-ImgSLI domain UI, injected here as the panels' row factory
    # (rating behavior callbacks come from the flyout's session glue).
    flyout.set_row_factory(
        make_rating_row_factory(
            get_rating=flyout._get_item_rating,
            increment_rating=flyout._increment_rating,
            decrement_rating=flyout._decrement_rating,
            create_rating_gesture=flyout._create_rating_gesture,
        )
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

    manager._font_popup_open = False

    manager._magn_popup_open = False
    manager._magn_popup_last_open_ts = 0.0
    manager._magn_instances_popup_open = False

def _connect_services(manager) -> None:
    font_manager = FontManager.get_instance()
    if font_manager is not None:
        font_manager.font_changed.connect(manager._on_font_changed)

    app = QApplication.instance()
    if isinstance(app, QApplication):
        app.focusChanged.connect(manager._on_app_focus_changed)
        app.installEventFilter(manager)
    if manager.parent_widget is not None:
        manager.parent_widget.installEventFilter(manager)
