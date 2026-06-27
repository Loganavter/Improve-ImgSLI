from __future__ import annotations

from PySide6.QtGui import QColor

from domain.qt_adapters import color_to_qcolor, qcolor_to_color
from ui.canvas_infra.scene.widget_contract import CanvasFeatureToolbarBinding

from .commands import (
    command_toggle_divider_visibility,
)
from .events import (
    SettingsSetDividerThicknessEvent,
    SettingsToggleDividerVisibilityEvent,
)
from .state import DividerWidgetState, get_divider_widget_state


def get_settings_presenter_from_window(presenter):
    window_presenter = getattr(presenter.main_window_app, "presenter", None)
    if window_presenter is not None and hasattr(window_presenter, "get_feature"):
        return window_presenter.get_feature("settings")
    return None


def toggle_toolbar_orientation(presenter, checked: bool) -> None:
    from core.state_management.actions import ToggleOrientationAction

    store = getattr(presenter, "store", None)
    if store is not None:

        dispatcher = getattr(store, "_dispatcher", None)
        if dispatcher is not None:
            dispatcher.dispatch(ToggleOrientationAction(checked), scope="viewport")

            if hasattr(store, "emit_viewport_change"):
                store.emit_viewport_change("interaction")


def set_toolbar_thickness(presenter, thickness: int) -> None:
    from ui.canvas_infra.scene.feature_state_api import execute_feature_command

    if isinstance(thickness, bool):
        return
    thickness = max(0, int(thickness))
    visible = thickness > 0
    store = getattr(presenter, "store", None)
    if store is not None:

        execute_feature_command(store, "divider", "toggle_visibility", visible)
        execute_feature_command(store, "divider", "set_thickness", thickness)
        return
    event_bus = getattr(presenter, "event_bus", None)
    if event_bus is not None:

        event_bus.emit(SettingsToggleDividerVisibilityEvent(visible))
        event_bus.emit(SettingsSetDividerThicknessEvent(thickness))
        return


def show_divider_color_picker(presenter) -> None:
    settings_presenter = get_settings_presenter_from_window(presenter)
    if settings_presenter is not None:

        def apply_selected(color):
            settings_controller = getattr(
                getattr(presenter, "main_controller", None),
                "settings",
                None,
            )
            if settings_controller is not None:
                settings_controller.execute_canvas_feature_command(
                    "divider",
                    "settings.set_color",
                    qcolor_to_color(color),
                )

        def post_apply(color):
            main_window = getattr(presenter, "main_window_app", None)
            if main_window is not None and hasattr(
                main_window, "set_divider_button_color"
            ):
                main_window.set_divider_button_color(color)

        settings_presenter.show_canvas_feature_color_picker(
            key="divider",
            setting_key="divider.color",
            title_key="ui.choose_divider_line_color",
            on_selected=apply_selected,
            post_apply=post_apply,
        )


def on_toolbar_middle_clicked(presenter) -> None:
    current_mode = getattr(presenter.store.settings, "ui_mode", "beginner")
    if current_mode != "expert":
        return
    button = presenter.ui.btn_orientation
    current_value = button.get_value()
    if current_value == 0:
        saved_value = button.get_saved_value()
        button.set_saved_value(None)
        target_value = (
            saved_value if (saved_value is not None and saved_value > 0) else 3
        )
        button.blockSignals(True)
        button.set_value(target_value)
        button.blockSignals(False)
        set_toolbar_thickness(presenter, target_value)
        return
    button.set_saved_value(current_value)
    button.blockSignals(True)
    button.set_value(0)
    button.blockSignals(False)
    set_toolbar_thickness(presenter, 0)


def _has_loaded_images(store) -> bool:
    document = getattr(store, "document", None)
    if document is None:
        return False
    return (
        getattr(document, "image1_path", None) is not None
        or getattr(document, "image2_path", None) is not None
    )


def sync_toolbar_state(presenter) -> None:
    ui = presenter.ui
    viewport = presenter.store.viewport
    divider_state = get_divider_widget_state(viewport.view_state)
    divider_thickness = 0 if not divider_state.visible else divider_state.thickness
    ui.btn_orientation.setChecked(
        viewport.view_state.is_horizontal,
        emit_signal=False,
    )
    if ui.btn_orientation.get_value() != divider_thickness:
        ui.btn_orientation.set_value(divider_thickness)
    current_mode = getattr(presenter.store.settings, "ui_mode", "beginner")
    ui.btn_orientation.setUnderlineColor(
        color_to_qcolor(divider_state.color)
        if current_mode == "expert"
        else QColor(0, 0, 0, 0)
    )
    if hasattr(ui, "btn_orientation_simple"):
        ui.btn_orientation_simple.setChecked(
            viewport.view_state.is_horizontal,
            emit_signal=False,
        )
    if hasattr(ui, "btn_divider_visible"):
        ui.btn_divider_visible.setChecked(not divider_state.visible, emit_signal=False)
    if hasattr(ui, "btn_divider_width"):
        if ui.btn_divider_width.get_value() != divider_thickness:
            ui.btn_divider_width.set_value(divider_thickness)
    if hasattr(ui, "btn_divider_color"):
        ui.btn_divider_color.setUnderlineColor(color_to_qcolor(divider_state.color))
    if hasattr(ui, "btn_magnifier_divider_width"):
        ui.btn_magnifier_divider_width.setUnderlineColor(
            color_to_qcolor(divider_state.color)
        )


class ToolbarViewportAdapter:
    def __init__(self, presenter):
        self.controller = getattr(presenter, "main_controller", None)
        self.store = presenter.store


def build_divider_toolbar_bindings() -> tuple[CanvasFeatureToolbarBinding, ...]:
    return (
        CanvasFeatureToolbarBinding(
            control_id="divider.orientation",
            on_toggled=toggle_toolbar_orientation,
            on_value_changed=set_toolbar_thickness,
            on_right_clicked=show_divider_color_picker,
            on_middle_clicked=on_toolbar_middle_clicked,
            sync_state=sync_toolbar_state,
        ),
        CanvasFeatureToolbarBinding(
            control_id="divider.orientation_simple",
            on_toggled=toggle_toolbar_orientation,
            sync_state=sync_toolbar_state,
        ),
        CanvasFeatureToolbarBinding(
            control_id="divider.visible",
            on_toggled=lambda presenter, checked: command_toggle_divider_visibility(
                ToolbarViewportAdapter(presenter),
                not checked,
            ),
            sync_state=sync_toolbar_state,
        ),
        CanvasFeatureToolbarBinding(
            control_id="divider.width",
            on_value_changed=set_toolbar_thickness,
            sync_state=sync_toolbar_state,
        ),
        CanvasFeatureToolbarBinding(
            control_id="divider.color",
            on_right_clicked=show_divider_color_picker,
            sync_state=sync_toolbar_state,
        ),
    )
