from PySide6.QtCore import Qt, QTimer

from ui.presenters.main_window.actions import (
    on_color_option_clicked,
    on_error_occurred,
    on_magnifier_element_hover_ended,
    on_magnifier_element_hovered,
    on_magnifier_guides_thickness_changed,
    on_magnifier_guides_toggled,
    on_ui_update_requested,
    on_update_requested,
    open_image_dialog,
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

def connect_signals(presenter):
    image_canvas = presenter.get_feature("image_canvas")
    export_presenter = presenter.get_feature("export")
    toolbar_presenter = presenter.get_feature("toolbar")
    settings_presenter = presenter.get_feature("settings")

    presenter.font_settings_flyout.closed.connect(
        lambda: on_font_flyout_closed(presenter)
    )
    presenter.font_settings_flyout.interaction_started.connect(
        lambda slider_name: _on_font_flyout_interaction_started(presenter, slider_name)
    )
    presenter.font_settings_flyout.interaction_finished.connect(
        lambda slider_name: _on_font_flyout_interaction_finished(presenter, slider_name)
    )
    presenter.store.state_changed.connect(
        lambda domain: on_store_state_changed(presenter, domain)
    )

    from domain.qt_adapters import qcolor_to_color
    from plugins.settings.events import SettingsApplyFontSettingsEvent

    if presenter.event_bus:
        presenter.font_settings_flyout.settings_changed.connect(
            lambda size, weight, color, bg_color, draw_bg, placement, alpha: presenter.event_bus.emit(
                SettingsApplyFontSettingsEvent(
                    size,
                    weight,
                    qcolor_to_color(color),
                    qcolor_to_color(bg_color),
                    draw_bg,
                    placement,
                    alpha,
                )
            )
        )
    else:
        presenter.font_settings_flyout.settings_changed.connect(
            presenter.main_controller.apply_font_settings
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
    presenter.main_controller.start_interactive_movement.connect(
        image_canvas.start_interactive_movement
    )
    presenter.main_controller.stop_interactive_movement.connect(
        image_canvas.stop_interactive_movement
    )

    presenter.widget.btn_image1.clicked.connect(lambda: open_image_dialog(presenter, 1))
    presenter.widget.btn_image2.clicked.connect(lambda: open_image_dialog(presenter, 2))
    presenter.widget.btn_text_settings.clicked.connect(
        lambda: presenter.ui_manager.transient.toggle_font_settings_flyout(
            anchor_widget=presenter.widget.btn_text_settings
        )
    )

    presenter._connect_button_action(
        presenter.widget.btn_quick_save,
        "quick_save",
        export_presenter.quick_save,
    )
    presenter.widget.btn_save.clicked.connect(export_presenter.save_result)
    presenter.ui.workspace_tabs.currentChanged.connect(
        lambda index: on_workspace_tab_changed(presenter, index)
    )
    presenter.ui.workspace_tabs.tabCloseRequested.connect(
        lambda index: on_workspace_tab_close_requested(presenter, index)
    )
    presenter.ui.workspace_tabs.addRequested.connect(
        lambda: on_new_workspace_tab_requested(presenter)
    )
    presenter.ui.workspace_tabs.tabContextMenuRequested.connect(
        lambda index, global_pos: on_workspace_tab_context_menu_requested(
            presenter, index, global_pos
        )
    )

    _connect_magnifier_color_controls(presenter)
    toolbar_presenter.connect_signals()
    _refresh_active_tab_actions()


def _refresh_active_tab_actions() -> None:
    from tabs.registry import get_shared_tab_registry
    from ui.actions.binder import resync_action_shortcuts
    from ui.actions.registry import get_action_registry
    from PySide6.QtWidgets import QApplication

    get_shared_tab_registry().create_service(
        "contribute_actions",
        get_action_registry(),
    )
    window = QApplication.activeWindow()
    if window is None:
        for top in QApplication.topLevelWidgets():
            if getattr(top, "presenter", None) is not None:
                window = top
                break
    resync_action_shortcuts(window)


def connect_event_handler_signals(presenter, event_handler):
    image_canvas = presenter.get_feature("image_canvas")
    toolbar_presenter = presenter.get_feature("toolbar")
    image_canvas.connect_event_handler_signals(event_handler)

    image_label = getattr(presenter.widget, "image_label", None)
    if image_label is not None:
        image_label.set_store(presenter.store)
        if hasattr(image_label, "set_session_controller"):
            sessions = getattr(presenter.main_controller, "sessions", None)
            if sessions is not None:
                image_label.set_session_controller(sessions)
        image_label.mousePressed.connect(
            event_handler.mouse_press_event_on_image_label_signal.emit
        )
        image_label.mouseMoved.connect(
            event_handler.mouse_move_event_on_image_label_signal.emit
        )
        image_label.mouseReleased.connect(
            event_handler.mouse_release_event_on_image_label_signal.emit
        )
        image_label.wheelScrolled.connect(
            event_handler.mouse_wheel_event_on_image_label_signal.emit
        )
        image_label.zoomChanged.connect(
            lambda _zoom: toolbar_presenter.update_toolbar_states()
        )
        widget = getattr(presenter, "widget", None)
        if widget is not None:
            image_label.zoomChanged.connect(widget.update_zoom_indicator)
        btn_zoom_reset = getattr(widget, "btn_zoom_reset", None) if widget is not None else None
        if btn_zoom_reset is not None:
            btn_zoom_reset.clicked.connect(lambda: image_label.reset_view())

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


def handle_global_mouse_press(presenter, event):
    if event.button() == Qt.MouseButton.RightButton:
        return
    global_pos = event.globalPosition()

    # Coalesce bursts (duplicate filters / synthetic presses) into one close.
    if getattr(presenter, "_popup_close_scheduled", False):
        return
    presenter._popup_close_scheduled = True

    def _close_popups():
        presenter._popup_close_scheduled = False
        presenter.ui_manager.transient.close_all_flyouts_if_needed(global_pos)

    QTimer.singleShot(0, _close_popups)


def on_font_flyout_closed(presenter):
    presenter.ui_manager.transient.mark_font_popup_closed()
    presenter.widget.btn_text_settings.setFlyoutOpen(False)


def _connect_magnifier_color_controls(presenter):
    settings_presenter = presenter.get_feature("settings")
    if hasattr(presenter.widget.btn_magnifier_color_settings, "set_store"):
        presenter.widget.btn_magnifier_color_settings.set_store(presenter.store)

    presenter.widget.btn_magnifier_color_settings.smartColorSetRequested.connect(
        settings_presenter.apply_smart_magnifier_colors
    )
    presenter.widget.btn_magnifier_color_settings.colorOptionClicked.connect(
        lambda option: on_color_option_clicked(presenter, option)
    )
    presenter.widget.btn_magnifier_color_settings.elementHovered.connect(
        lambda element_name: on_magnifier_element_hovered(presenter, element_name)
    )
    presenter.widget.btn_magnifier_color_settings.elementHoverEnded.connect(
        lambda: on_magnifier_element_hover_ended(presenter)
    )

    if hasattr(presenter.widget, "btn_magnifier_color_settings_beginner"):
        if hasattr(presenter.widget.btn_magnifier_color_settings_beginner, "set_store"):
            presenter.widget.btn_magnifier_color_settings_beginner.set_store(
                presenter.store
            )
        presenter.widget.btn_magnifier_color_settings_beginner.smartColorSetRequested.connect(
            settings_presenter.apply_smart_magnifier_colors
        )
        presenter.widget.btn_magnifier_color_settings_beginner.colorOptionClicked.connect(
            lambda option: on_color_option_clicked(presenter, option)
        )
        presenter.widget.btn_magnifier_color_settings_beginner.elementHovered.connect(
            lambda element_name: on_magnifier_element_hovered(presenter, element_name)
        )
        presenter.widget.btn_magnifier_color_settings_beginner.elementHoverEnded.connect(
            lambda: on_magnifier_element_hover_ended(presenter)
        )

    presenter.widget.btn_magnifier_guides.toggled.connect(
        lambda checked: on_magnifier_guides_toggled(presenter, not checked)
    )
    presenter.widget.btn_magnifier_guides.valueChanged.connect(
        lambda value: on_magnifier_guides_thickness_changed(presenter, value)
    )

    if hasattr(presenter.widget, "btn_magnifier_guides_simple"):
        presenter.widget.btn_magnifier_guides_simple.toggled.connect(
            lambda checked: on_magnifier_guides_toggled(presenter, checked)
        )
    # btn_magnifier_guides_width.valueChanged is wired by the owning tab's
    # own toolbar_presenter connect_signals() (control_id "guides.thickness")
    # — not here, to avoid a double connection.


def _on_font_flyout_interaction_started(presenter, slider_name: str) -> None:
    viewport_ctrl = getattr(
        getattr(presenter, "main_controller", None), "viewport_plugin", None
    )
    if viewport_ctrl is not None and hasattr(viewport_ctrl, "on_slider_pressed"):
        viewport_ctrl.on_slider_pressed(slider_name)


def _on_font_flyout_interaction_finished(presenter, slider_name: str) -> None:
    viewport_ctrl = getattr(
        getattr(presenter, "main_controller", None), "viewport_plugin", None
    )
    if viewport_ctrl is not None and hasattr(viewport_ctrl, "on_slider_released"):
        viewport_ctrl.on_slider_released(slider_name)
