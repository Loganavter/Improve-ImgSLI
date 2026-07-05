from __future__ import annotations

from domain.qt_adapters import color_to_qcolor
from ui.canvas_infra.scene.widget_contract import CanvasFeatureToolbarBinding
from ui.canvas_infra.scene.widget_registry import get_canvas_feature_command_by_alias

from .commands import command_set_guides_thickness
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


def _query_active_show_laser(store) -> bool:
    query = get_canvas_feature_command_by_alias("overlay.active_state")
    if query is None or store is None:
        return False
    active = query(store) or {}
    return bool(active.get("show_laser", False))


def _toggle_active_magnifier_laser(presenter, enabled: bool) -> None:
    store = getattr(presenter, "store", None)
    if store is None:
        return
    cmd = get_canvas_feature_command_by_alias("overlay.set_active_laser_enabled")
    if cmd is not None:
        cmd(store, bool(enabled))
    if enabled and not get_guides_widget_state(store.viewport.view_state).enabled:
        toggle_cmd = get_canvas_feature_command_by_alias("guides.toggle_enabled")
        if toggle_cmd is None:
            toggle_cmd = get_canvas_feature_command_by_alias("viewport.toggle_enabled")
        if toggle_cmd is not None:
            toggle_cmd(store, True)


def sync_guides_toolbar_state(presenter) -> None:
    state = get_guides_widget_state(presenter.store.viewport.view_state)
    ui = getattr(presenter, "ui", None)
    active_laser = _query_active_show_laser(presenter.store)

    btn_guides = getattr(ui, "btn_magnifier_guides", None)
    if btn_guides is not None:
        if active_laser:
            set_checked_quietly(btn_guides, False)
            set_slider_value_quietly(btn_guides, max(1, int(state.thickness)))
        else:
            if btn_guides.get_value() > 0:
                btn_guides.set_saved_value(btn_guides.get_value())
            set_slider_value_quietly(btn_guides, 0)
            set_checked_quietly(btn_guides, True)
        btn_guides.setUnderlineColor(color_to_qcolor(state.color))
    set_checked_quietly(
        getattr(ui, "btn_magnifier_guides_simple", None), bool(active_laser)
    )
    btn_guides_width = getattr(ui, "btn_magnifier_guides_width", None)
    if btn_guides_width is not None:
        set_slider_value_quietly(btn_guides_width, int(state.thickness))
        btn_guides_width.setUnderlineColor(color_to_qcolor(state.color))


def build_guides_toolbar_bindings() -> tuple[CanvasFeatureToolbarBinding, ...]:
    return (
        CanvasFeatureToolbarBinding(
            control_id="guides.enabled",
            on_toggled=_toggle_active_magnifier_laser,
            on_value_changed=command_set_guides_thickness,
            on_right_clicked=show_guides_color_picker,
            sync_state=sync_guides_toolbar_state,
        ),
        CanvasFeatureToolbarBinding(
            control_id="guides.enabled_simple",
            on_toggled=_toggle_active_magnifier_laser,
            sync_state=sync_guides_toolbar_state,
        ),
        CanvasFeatureToolbarBinding(
            control_id="guides.thickness",
            on_value_changed=command_set_guides_thickness,
            sync_state=sync_guides_toolbar_state,
        ),
    )
