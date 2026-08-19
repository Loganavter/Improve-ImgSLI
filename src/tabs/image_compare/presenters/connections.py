from PySide6.QtCore import QTimer

from tabs.image_compare.presenters.actions import (
    on_color_option_clicked,
    on_magnifier_element_hover_ended,
    on_magnifier_element_hovered,
    on_magnifier_guides_thickness_changed,
    on_magnifier_guides_toggled,
    open_image_dialog,
)
from tabs.image_compare.canvas.contracts import BaseCanvasProtocol
from tabs.image_compare.canvas.helpers import get_canvas


def connect_signals(presenter):
    image_canvas = presenter.get_feature("image_canvas")
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

    presenter.main_controller.start_interactive_movement.connect(
        image_canvas.start_interactive_movement
    )
    presenter.main_controller.stop_interactive_movement.connect(
        image_canvas.stop_interactive_movement
    )

    presenter.ui.btn_image1.clicked.connect(lambda: open_image_dialog(presenter, 1))
    presenter.ui.btn_image2.clicked.connect(lambda: open_image_dialog(presenter, 2))
    presenter.ui.btn_text_settings.clicked.connect(
        lambda: presenter.ui_manager.transient.toggle_font_settings_flyout(
            anchor_widget=presenter.ui.btn_text_settings
        )
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
        ui = getattr(presenter, "ui", None)
        if ui is not None and hasattr(ui, "update_zoom_indicator"):
            image_label.zoomChanged.connect(ui.update_zoom_indicator)
        btn_zoom_reset = getattr(ui, "btn_zoom_reset", None) if ui is not None else None
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


def handle_global_mouse_press(presenter, event):
    global_pos = event.globalPosition()

    def _close_popups():
        presenter.ui_manager.transient.close_all_flyouts_if_needed(global_pos)

    QTimer.singleShot(0, _close_popups)


def on_font_flyout_closed(presenter):
    presenter.ui_manager.transient.mark_font_popup_closed()
    presenter.ui.btn_text_settings.setFlyoutOpen(False)


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
            presenter.ui.btn_magnifier_color_settings_beginner.set_store(
                presenter.store
            )
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
        lambda checked: on_magnifier_guides_toggled(presenter, not checked)
    )
    # TODO: btn_magnifier_guides.valueChanged removed with Button 0.2.16 scroll feature
    # Re-implement via WheelCounterCapability + custom UI layer if needed

    if hasattr(presenter.ui, "btn_magnifier_guides_simple"):
        presenter.ui.btn_magnifier_guides_simple.toggled.connect(
            lambda checked: on_magnifier_guides_toggled(presenter, checked)
        )
    # btn_magnifier_guides_width.valueChanged is wired in
    # presenters/toolbar/connections.py (control_id "guides.thickness").


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
