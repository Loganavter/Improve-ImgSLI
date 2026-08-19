from __future__ import annotations

import logging

from PySide6.QtWidgets import QApplication

from shared_toolkit.ui.managers.font_manager import FontManager

logger = logging.getLogger("ImproveImgSLI")

def initialize_ui_manager_pre_transient(manager) -> None:
    _init_unified_flyout(manager)
    _init_popup_state(manager)
    _init_magnifier_flyout_widget(manager)

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

def _init_magnifier_flyout_widget(manager) -> None:
    # MagnifierVisibilityFlyout is tab-owned — created by image_compare
    # in assemble_host_page(), NOT by the host.
    pass

def _connect_magnifier_visibility_buttons(manager) -> None:
    if manager.main_controller is None:
        return

    from ui.canvas_infra.scene.feature_state_api import execute_feature_command

    flyout = manager.magnifier_visibility_flyout
    store = manager.store

    if store is not None:
        flyout.btn_left.toggled.connect(
            lambda checked: execute_feature_command(
                store, "magnifier", "set_active_visibility_parts",
                left=not checked,
                center=query_current_visibility(store, "center"),
                right=query_current_visibility(store, "right"),
            )
        )
        flyout.btn_right.toggled.connect(
            lambda checked: execute_feature_command(
                store, "magnifier", "set_active_visibility_parts",
                left=query_current_visibility(store, "left"),
                center=query_current_visibility(store, "center"),
                right=not checked,
            )
        )
        flyout.btn_center.toggled.connect(
            lambda checked: execute_feature_command(
                store, "magnifier", "set_active_visibility_parts",
                left=query_current_visibility(store, "left"),
                center=not checked,
                right=query_current_visibility(store, "right"),
            )
        )
        return

    logger.warning(
        "UIManager: Cannot connect magnifier visibility flyout buttons - no store available"
    )

def query_current_visibility(store, part: str) -> bool:
    """Query current visibility of a magnifier part."""
    from ui.canvas_infra.scene.feature_state_api import query_feature_state
    state = query_feature_state(store, "magnifier", "active_state")
    if state is None:
        return True
    part_key = f"visible_{part}"
    return bool(state.get(part_key, True))

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
