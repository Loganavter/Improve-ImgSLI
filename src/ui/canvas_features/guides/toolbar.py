from __future__ import annotations

from ui.canvas_infra.scene.widget_contract import CanvasFeatureToolbarBinding

from .commands import command_set_guides_thickness, command_toggle_guides
from .state import get_guides_widget_state

def set_slider_value_quietly(control, value: int) -> None:
    if control is None or control.get_value() == value:
        return
    control.blockSignals(True)
    try:
        control.set_value(value)
    finally:
        control.blockSignals(False)

def set_checked_quietly(control, value: bool) -> None:
    if control is None or control.isChecked() == value:
        return
    control.setChecked(value, emit_signal=False)

def show_guides_color_picker(presenter) -> None:
    window_presenter = getattr(presenter.main_window_app, "presenter", None)
    if window_presenter is None or not hasattr(window_presenter, "get_feature"):
        return
    settings_presenter = window_presenter.get_feature("settings")
    if settings_presenter is not None:
        settings_presenter.show_laser_color_picker()

def sync_guides_toolbar_state(presenter) -> None:
    state = get_guides_widget_state(presenter.store.viewport.view_state)
    ui = getattr(presenter, "ui", None)

    btn_guides = getattr(ui, "btn_magnifier_guides", None)
    if btn_guides is not None:
        if state.enabled:
            set_checked_quietly(btn_guides, False)
            set_slider_value_quietly(btn_guides, max(1, int(state.thickness)))
        else:
            if btn_guides.get_value() > 0:
                btn_guides.set_saved_value(btn_guides.get_value())
            set_slider_value_quietly(btn_guides, 0)
            set_checked_quietly(btn_guides, True)
    set_checked_quietly(getattr(ui, "btn_magnifier_guides_simple", None), bool(state.enabled))
    set_slider_value_quietly(getattr(ui, "btn_magnifier_guides_width", None), int(state.thickness))

def build_guides_toolbar_bindings() -> tuple[CanvasFeatureToolbarBinding, ...]:
    return (
        CanvasFeatureToolbarBinding(
            control_id="guides.enabled",
            on_toggled=command_toggle_guides,
            on_value_changed=command_set_guides_thickness,
            on_right_clicked=show_guides_color_picker,
            sync_state=sync_guides_toolbar_state,
        ),
        CanvasFeatureToolbarBinding(
            control_id="guides.enabled_simple",
            on_toggled=command_toggle_guides,
            sync_state=sync_guides_toolbar_state,
        ),
        CanvasFeatureToolbarBinding(
            control_id="guides.thickness",
            on_value_changed=command_set_guides_thickness,
            sync_state=sync_guides_toolbar_state,
        ),
    )

