from PyQt6.QtCore import QSize

from core.events import (
    SettingsSetDividerLineThicknessEvent,
    SettingsSetMagnifierDividerThicknessEvent,
    SettingsToggleDividerLineVisibilityEvent,
    SettingsToggleMagnifierDividerVisibilityEvent,
    ViewportToggleMagnifierOrientationEvent,
)
from ui.icon_manager import AppIcon, get_app_icon
from shared_toolkit.ui.overlay_layer import get_overlay_layer

def on_ui_divider_thickness_changed(presenter, thickness):
    presenter.event_bus.emit(SettingsSetDividerLineThicknessEvent(thickness))
    presenter.event_bus.emit(
        SettingsToggleDividerLineVisibilityEvent(thickness == 0)
    )

def on_ui_magnifier_thickness_changed(presenter, thickness):
    presenter.event_bus.emit(SettingsSetMagnifierDividerThicknessEvent(thickness))
    presenter.event_bus.emit(
        SettingsToggleMagnifierDividerVisibilityEvent(thickness == 0)
    )

def on_interpolation_combo_clicked(presenter):
    if presenter.ui_manager:
        presenter.ui_manager.toggle_interpolation_flyout()

def on_orientation_right_clicked(presenter):
    current_mode = getattr(presenter.store.settings, "ui_mode", "beginner")
    if current_mode == "advanced":
        show_magnifier_orientation_popup(presenter)
        _toggle_magnifier_orientation(presenter)
        return
    presenter._show_divider_color_picker()

def show_magnifier_orientation_popup(presenter):
    current_orientation = presenter.store.viewport.magnifier_is_horizontal
    icon_enum = (
        AppIcon.HORIZONTAL_SPLIT
        if not current_orientation
        else AppIcon.VERTICAL_SPLIT
    )
    overlay_layer = get_overlay_layer(presenter.ui.btn_orientation)
    if overlay_layer is None:
        return

    overlay_layer.show_popup(
        "orientation_popup",
        presenter.ui.btn_orientation,
        pixmap=get_app_icon(icon_enum).pixmap(18, 18),
        size=QSize(32, 28),
        position="top",
        offset=6,
        timeout_ms=800,
    )

def on_magnifier_orientation_right_clicked(presenter):
    current_mode = getattr(presenter.store.settings, "ui_mode", "beginner")
    if current_mode == "advanced":
        _toggle_magnifier_orientation(presenter)
        return
    presenter._show_magnifier_divider_color_picker()

def on_orientation_middle_clicked(presenter):
    current_mode = getattr(presenter.store.settings, "ui_mode", "beginner")
    if current_mode != "expert":
        return

    button = presenter.ui.btn_orientation
    current_value = button.get_value()
    if current_value == 0:
        saved_value = button.restore_saved_value()
        target_value = saved_value if (saved_value is not None and saved_value > 0) else 3
        button.blockSignals(True)
        button.set_value(target_value)
        button.blockSignals(False)
        if presenter.event_bus:
            presenter.event_bus.emit(SettingsToggleDividerLineVisibilityEvent(True))
            presenter.event_bus.emit(SettingsSetDividerLineThicknessEvent(target_value))
        elif presenter.main_controller:
            presenter.main_controller.toggle_divider_line_visibility(True)
            presenter.main_controller.set_divider_line_thickness(target_value)
        return

    button.set_saved_value(current_value)
    button.blockSignals(True)
    button.set_value(0)
    button.blockSignals(False)
    if presenter.event_bus:
        presenter.event_bus.emit(SettingsToggleDividerLineVisibilityEvent(False))
        presenter.event_bus.emit(SettingsSetDividerLineThicknessEvent(0))
    elif presenter.main_controller:
        presenter.main_controller.toggle_divider_line_visibility(False)
        presenter.main_controller.set_divider_line_thickness(0)

def on_magnifier_orientation_middle_clicked(presenter):
    current_mode = getattr(presenter.store.settings, "ui_mode", "beginner")
    if current_mode != "expert":
        return

    button = presenter.ui.btn_magnifier_orientation
    current_value = button.get_value()
    if current_value == 0:
        saved_value = button.restore_saved_value()
        target_value = saved_value if (saved_value is not None and saved_value > 0) else 3
        button.blockSignals(True)
        button.set_value(target_value)
        button.blockSignals(False)
        if presenter.event_bus:
            presenter.event_bus.emit(
                SettingsToggleMagnifierDividerVisibilityEvent(True)
            )
            presenter.event_bus.emit(
                SettingsSetMagnifierDividerThicknessEvent(target_value)
            )
        elif presenter.main_controller:
            if hasattr(presenter.main_controller, "settings_ctrl"):
                presenter.main_controller.settings_ctrl.toggle_magnifier_divider_visibility(
                    True
                )
            presenter.main_controller.set_magnifier_divider_thickness(target_value)
        return

    button.set_saved_value(current_value)
    button.blockSignals(True)
    button.set_value(0)
    button.blockSignals(False)
    if presenter.event_bus:
        presenter.event_bus.emit(SettingsToggleMagnifierDividerVisibilityEvent(False))
        presenter.event_bus.emit(SettingsSetMagnifierDividerThicknessEvent(0))
    elif presenter.main_controller:
        if hasattr(presenter.main_controller, "settings_ctrl"):
            presenter.main_controller.settings_ctrl.toggle_magnifier_divider_visibility(
                False
            )
        presenter.main_controller.set_magnifier_divider_thickness(0)

def toggle_magnifier_divider_visibility(presenter):
    visible = not presenter.store.viewport.magnifier_divider_visible
    if presenter.event_bus is not None:
        presenter.event_bus.emit(
            SettingsToggleMagnifierDividerVisibilityEvent(visible)
        )
        return

    if (
        presenter.main_controller is not None
        and presenter.main_controller.settings_ctrl is not None
        and hasattr(
            presenter.main_controller.settings_ctrl,
            "toggle_magnifier_divider_visibility",
        )
    ):
        presenter.main_controller.settings_ctrl.toggle_magnifier_divider_visibility(
            visible
        )

def update_magnifier_orientation_button_state(presenter):
    presenter.ui.btn_magnifier_orientation.setChecked(
        presenter.store.viewport.magnifier_is_horizontal,
        emit_signal=False,
    )

def _toggle_magnifier_orientation(presenter):
    current_orientation = presenter.store.viewport.magnifier_is_horizontal
    new_value = not current_orientation
    if presenter.event_bus:
        presenter.event_bus.emit(ViewportToggleMagnifierOrientationEvent(new_value))
    elif presenter.main_controller:
        presenter.main_controller.toggle_magnifier_orientation(new_value)
