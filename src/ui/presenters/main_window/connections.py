from PyQt6.QtCore import QTimer

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
    on_video_session_advance_requested,
    on_video_session_attach_resource_requested,
    on_video_session_create_image_compare_requested,
    on_workspace_session_triggered,
    on_workspace_tab_changed,
)
from ui.widgets.gl_canvas.contracts import BaseCanvasProtocol
from ui.widgets.gl_canvas.helpers import get_canvas

def connect_signals(presenter):
    image_canvas = presenter.get_feature("image_canvas")
    export_presenter = presenter.get_feature("export")
    toolbar_presenter = presenter.get_feature("toolbar")
    settings_presenter = presenter.get_feature("settings")

    presenter.font_settings_flyout.closed.connect(
        lambda: on_font_flyout_closed(presenter)
    )
    presenter.store.state_changed.connect(
        lambda domain: on_store_state_changed(presenter, domain)
    )

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

    presenter.ui.btn_image1.clicked.connect(lambda: open_image_dialog(presenter, 1))
    presenter.ui.btn_image2.clicked.connect(lambda: open_image_dialog(presenter, 2))
    presenter.ui.btn_color_picker.clicked.connect(
        lambda: presenter.ui_manager.transient.toggle_font_settings_flyout(
            anchor_widget=presenter.ui.btn_color_picker
        )
    )

    presenter._connect_button_action(
        presenter.ui.btn_quick_save,
        "quick_save",
        export_presenter.quick_save,
    )
    presenter.ui.btn_save.clicked.connect(export_presenter.save_result)
    presenter.ui.workspace_tabs.currentChanged.connect(
        lambda index: on_workspace_tab_changed(presenter, index)
    )
    presenter.ui.btn_new_session.triggered.connect(
        lambda action: on_workspace_session_triggered(presenter, action)
    )
    presenter.ui.video_session_widget.advance_timeline_requested.connect(
        lambda: on_video_session_advance_requested(presenter)
    )
    presenter.ui.video_session_widget.attach_resource_requested.connect(
        lambda: on_video_session_attach_resource_requested(presenter)
    )
    presenter.ui.video_session_widget.create_image_compare_requested.connect(
        lambda: on_video_session_create_image_compare_requested(presenter)
    )

    _connect_magnifier_color_controls(presenter)
    toolbar_presenter.connect_signals()

def connect_event_handler_signals(presenter, event_handler):
    image_canvas = presenter.get_feature("image_canvas")
    toolbar_presenter = presenter.get_feature("toolbar")
    image_canvas.connect_event_handler_signals(event_handler)

    image_label: BaseCanvasProtocol | None = get_canvas(presenter.ui)
    if image_label is not None:
        image_label.set_store(presenter.store)
        image_label.mousePressed.connect(
            event_handler.mouse_press_event_on_image_label_signal.emit
        )
        image_label.mouseMoved.connect(
            event_handler.mouse_move_event_on_image_label_signal.emit
        )
        image_label.mouseReleased.connect(
            event_handler.mouse_release_event_on_image_label_signal.emit
        )
        image_label.keyPressed.connect(
            event_handler.keyboard_press_event_signal.emit
        )
        image_label.keyReleased.connect(
            event_handler.keyboard_release_event_signal.emit
        )
        image_label.wheelScrolled.connect(
            event_handler.mouse_wheel_event_on_image_label_signal.emit
        )
        image_label.zoomChanged.connect(
            lambda _zoom: toolbar_presenter.update_toolbar_states()
        )

    event_handler.mouse_press_event_signal.connect(
        lambda event: handle_global_mouse_press(presenter, event)
    )
    presenter.main_controller.start_interactive_movement.connect(
        event_handler.start_interactive_movement
    )
    presenter.main_controller.stop_interactive_movement.connect(
        event_handler.stop_interactive_movement
    )

def on_interpolation_combo_clicked(presenter):
    presenter.ui_manager.transient.toggle_interpolation_flyout()

def repopulate_flyouts(presenter):
    if presenter.ui_manager:
        presenter.ui_manager.transient.repopulate_flyouts()

def handle_global_mouse_press(presenter, event):
    global_pos = event.globalPosition()

    def _close_popups():
        presenter.ui_manager.transient.close_all_flyouts_if_needed(global_pos)

    QTimer.singleShot(0, _close_popups)

def on_font_flyout_closed(presenter):
    presenter.ui_manager.transient.mark_font_popup_closed()
    presenter.ui.btn_color_picker.setFlyoutOpen(False)

def _connect_magnifier_color_controls(presenter):
    settings_presenter = presenter.get_feature("settings")
    if hasattr(presenter.ui.btn_magnifier_color_settings, "set_store"):
        presenter.ui.btn_magnifier_color_settings.set_store(presenter.store)

    presenter.ui.btn_magnifier_color_settings.smartColorSetRequested.connect(
        settings_presenter.apply_smart_magnifier_colors
    )
    presenter.ui.btn_magnifier_color_settings.colorOptionClicked.connect(
        lambda option: on_color_option_clicked(presenter, option)
    )
    presenter.ui.btn_magnifier_color_settings.elementHovered.connect(
        lambda element_name: on_magnifier_element_hovered(presenter, element_name)
    )
    presenter.ui.btn_magnifier_color_settings.elementHoverEnded.connect(
        lambda: on_magnifier_element_hover_ended(presenter)
    )

    if hasattr(presenter.ui, "btn_magnifier_color_settings_beginner"):
        if hasattr(presenter.ui.btn_magnifier_color_settings_beginner, "set_store"):
            presenter.ui.btn_magnifier_color_settings_beginner.set_store(presenter.store)
        presenter.ui.btn_magnifier_color_settings_beginner.smartColorSetRequested.connect(
            settings_presenter.apply_smart_magnifier_colors
        )
        presenter.ui.btn_magnifier_color_settings_beginner.colorOptionClicked.connect(
            lambda option: on_color_option_clicked(presenter, option)
        )
        presenter.ui.btn_magnifier_color_settings_beginner.elementHovered.connect(
            lambda element_name: on_magnifier_element_hovered(presenter, element_name)
        )
        presenter.ui.btn_magnifier_color_settings_beginner.elementHoverEnded.connect(
            lambda: on_magnifier_element_hover_ended(presenter)
        )

    presenter.ui.btn_magnifier_guides.toggled.connect(
        lambda checked: on_magnifier_guides_toggled(presenter, checked)
    )
    presenter.ui.btn_magnifier_guides.valueChanged.connect(
        lambda thickness: on_magnifier_guides_thickness_changed(presenter, thickness)
    )

    if hasattr(presenter.ui, "btn_magnifier_guides_simple"):
        presenter.ui.btn_magnifier_guides_simple.toggled.connect(
            lambda checked: on_magnifier_guides_toggled(presenter, checked)
        )
    if hasattr(presenter.ui, "btn_magnifier_guides_width"):
        presenter.ui.btn_magnifier_guides_width.valueChanged.connect(
            lambda thickness: on_magnifier_guides_thickness_changed(presenter, thickness)
        )
