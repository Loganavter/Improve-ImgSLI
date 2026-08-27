from __future__ import annotations

from domain.qt_adapters import ensure_visible_qcolor
from ui.canvas_infra.scene.widget_contract import CanvasFeatureToolbarBinding
from tabs.image_compare.canvas.registry import registry

from tabs.image_compare.canvas.features.guides.commands.registry import command_set_guides_thickness
from tabs.image_compare.canvas.features.guides.state.feature_state import get_guides_widget_state


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


def _toggle_active_magnifier_laser(presenter, enabled: bool) -> None:
    store = getattr(presenter, "store", None)
    if store is None:
        return
    enabled = bool(enabled)
    cmd = registry().get_feature_command_by_alias("overlay.set_active_laser_enabled")
    if cmd is not None:
        cmd(store, enabled)
    # The canvas only draws guide lines when the *global* guides.enabled flag
    # is set (see build_magnifier_layout's guide_sets gating) — show_laser is
    # purely per-magnifier UI state and isn't consulted by the renderer. So
    # this toggle must keep the global flag in sync on both edges, not just
    # when turning it on, or turning it off here leaves the laser drawn.
    if enabled != get_guides_widget_state(store.viewport.view_state).enabled:
        toggle_cmd = registry().get_feature_command_by_alias("guides.toggle_enabled")
        if toggle_cmd is None:
            toggle_cmd = registry().get_feature_command_by_alias("viewport.toggle_enabled")
        if toggle_cmd is not None:
            toggle_cmd(store, enabled)


def sync_guides_toolbar_state(presenter) -> None:
    state = get_guides_widget_state(presenter.store.viewport.view_state)
    ui = getattr(presenter, "widget", None)

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
        btn_guides.setUnderlineColor(ensure_visible_qcolor(state.color))
    set_checked_quietly(
        getattr(ui, "btn_magnifier_guides_simple", None), bool(state.enabled)
    )
    btn_guides_width = getattr(ui, "btn_magnifier_guides_width", None)
    if btn_guides_width is not None:
        set_slider_value_quietly(btn_guides_width, int(state.thickness))
        btn_guides_width.setUnderlineColor(ensure_visible_qcolor(state.color))


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
