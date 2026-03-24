from PyQt6.QtCore import QTimer

def connect_signals(presenter):
    presenter.font_settings_flyout.closed.connect(presenter._on_font_flyout_closed)
    presenter.store.state_changed.connect(presenter._on_store_state_changed)

    from core.events import SettingsApplyFontSettingsEvent
    from domain.qt_adapters import qcolor_to_color

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

    presenter.main_controller.error_occurred.connect(presenter._on_error_occurred)
    presenter.main_controller.update_requested.connect(presenter._on_update_requested)
    presenter.main_controller.ui_update_requested.connect(
        presenter._on_ui_update_requested
    )
    presenter.main_controller.start_interactive_movement.connect(
        presenter.start_interactive_movement
    )
    presenter.main_controller.stop_interactive_movement.connect(
        presenter.stop_interactive_movement
    )
    presenter.main_controller.start_interactive_movement.connect(
        presenter.image_canvas_presenter.start_interactive_movement
    )
    presenter.main_controller.stop_interactive_movement.connect(
        presenter.image_canvas_presenter.stop_interactive_movement
    )

    presenter.ui.btn_image1.clicked.connect(lambda: presenter._open_image_dialog(1))
    presenter.ui.btn_image2.clicked.connect(lambda: presenter._open_image_dialog(2))
    presenter.ui.btn_color_picker.clicked.connect(
        lambda: presenter.ui_manager.toggle_font_settings_flyout(
            anchor_widget=presenter.ui.btn_color_picker
        )
    )

    presenter._connect_button_action(
        presenter.ui.btn_quick_save,
        "quick_save",
        presenter.export_presenter.quick_save,
    )
    presenter.ui.btn_save.clicked.connect(presenter.export_presenter.save_result)
    presenter.ui.workspace_tabs.currentChanged.connect(
        presenter._on_workspace_tab_changed
    )
    presenter.ui.btn_new_session.triggered.connect(
        presenter._on_workspace_session_triggered
    )
    presenter.ui.video_session_widget.advance_timeline_requested.connect(
        presenter._on_video_session_advance_requested
    )
    presenter.ui.video_session_widget.attach_resource_requested.connect(
        presenter._on_video_session_attach_resource_requested
    )
    presenter.ui.video_session_widget.create_image_compare_requested.connect(
        presenter._on_video_session_create_image_compare_requested
    )

    _connect_magnifier_color_controls(presenter)
    presenter.toolbar_presenter.connect_signals()

def connect_event_handler_signals(presenter, event_handler):
    presenter.image_canvas_presenter.connect_event_handler_signals(event_handler)

    if hasattr(presenter.ui, "image_label"):
        if hasattr(presenter.ui.image_label, "set_store"):
            presenter.ui.image_label.set_store(presenter.store)
        presenter.ui.image_label.mousePressed.connect(
            event_handler.mouse_press_event_on_image_label_signal.emit
        )
        presenter.ui.image_label.mouseMoved.connect(
            event_handler.mouse_move_event_on_image_label_signal.emit
        )
        presenter.ui.image_label.mouseReleased.connect(
            event_handler.mouse_release_event_on_image_label_signal.emit
        )
        presenter.ui.image_label.keyPressed.connect(
            event_handler.keyboard_press_event_signal.emit
        )
        presenter.ui.image_label.keyReleased.connect(
            event_handler.keyboard_release_event_signal.emit
        )
        presenter.ui.image_label.wheelScrolled.connect(
            event_handler.mouse_wheel_event_on_image_label_signal.emit
        )
        if hasattr(presenter.ui.image_label, "zoomChanged"):
            presenter.ui.image_label.zoomChanged.connect(
                lambda _zoom: presenter.toolbar_presenter.update_toolbar_states()
            )

    event_handler.mouse_press_event_signal.connect(presenter._handle_global_mouse_press)
    presenter.main_controller.start_interactive_movement.connect(
        event_handler.start_interactive_movement
    )
    presenter.main_controller.stop_interactive_movement.connect(
        event_handler.stop_interactive_movement
    )

def on_interpolation_combo_clicked(presenter):
    presenter.ui_manager.toggle_interpolation_flyout()

def repopulate_flyouts(presenter):
    if presenter.ui_manager:
        presenter.ui_manager.repopulate_flyouts()

def handle_global_mouse_press(presenter, event):
    global_pos = event.globalPosition()

    def _close_popups():
        presenter.ui_manager.close_all_flyouts_if_needed(global_pos)

    QTimer.singleShot(0, _close_popups)

def on_font_flyout_closed(presenter):
    presenter.ui_manager._font_popup_open = False
    presenter.ui.btn_color_picker.setFlyoutOpen(False)

def _connect_magnifier_color_controls(presenter):
    if hasattr(presenter.ui.btn_magnifier_color_settings, "set_store"):
        presenter.ui.btn_magnifier_color_settings.set_store(presenter.store)

    presenter.ui.btn_magnifier_color_settings.smartColorSetRequested.connect(
        presenter.settings_presenter.apply_smart_magnifier_colors
    )
    presenter.ui.btn_magnifier_color_settings.colorOptionClicked.connect(
        presenter._on_color_option_clicked
    )
    presenter.ui.btn_magnifier_color_settings.elementHovered.connect(
        presenter._on_magnifier_element_hovered
    )
    presenter.ui.btn_magnifier_color_settings.elementHoverEnded.connect(
        presenter._on_magnifier_element_hover_ended
    )

    if hasattr(presenter.ui, "btn_magnifier_color_settings_beginner"):
        if hasattr(presenter.ui.btn_magnifier_color_settings_beginner, "set_store"):
            presenter.ui.btn_magnifier_color_settings_beginner.set_store(presenter.store)
        presenter.ui.btn_magnifier_color_settings_beginner.smartColorSetRequested.connect(
            presenter.settings_presenter.apply_smart_magnifier_colors
        )
        presenter.ui.btn_magnifier_color_settings_beginner.colorOptionClicked.connect(
            presenter._on_color_option_clicked
        )
        presenter.ui.btn_magnifier_color_settings_beginner.elementHovered.connect(
            presenter._on_magnifier_element_hovered
        )
        presenter.ui.btn_magnifier_color_settings_beginner.elementHoverEnded.connect(
            presenter._on_magnifier_element_hover_ended
        )

    presenter.ui.btn_magnifier_guides.toggled.connect(
        presenter._on_magnifier_guides_toggled
    )
    presenter.ui.btn_magnifier_guides.valueChanged.connect(
        presenter._on_magnifier_guides_thickness_changed
    )

    if hasattr(presenter.ui, "btn_magnifier_guides_simple"):
        presenter.ui.btn_magnifier_guides_simple.toggled.connect(
            presenter._on_magnifier_guides_toggled
        )
    if hasattr(presenter.ui, "btn_magnifier_guides_width"):
        presenter.ui.btn_magnifier_guides_width.valueChanged.connect(
            presenter._on_magnifier_guides_thickness_changed
        )
