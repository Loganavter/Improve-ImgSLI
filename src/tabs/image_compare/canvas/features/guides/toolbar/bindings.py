from __future__ import annotations

from domain.qt_adapters import ensure_visible_qcolor
from ui.canvas_infra.scene.widget_contract import CanvasFeatureToolbarBinding
from tabs.image_compare.canvas.registry import registry

from tabs.image_compare.canvas.features.guides.commands.registry import command_set_guides_thickness
from tabs.image_compare.canvas.features.guides.state.feature_state import get_guides_widget_state


def set_slider_value_quietly(control, value: int) -> None:
    if control is None or control.get_value() == value:
        return
    # Must not emit valueChanged on hover/sync — valueChanged is the only path that
    # dispatches SetGuidesThicknessAction which also clears show_laser via
    # _sync_active_laser_enabled. Emitting on hover would disable lasers.
    control.blockSignals(True)
    try:
        try:
            control.set_value(value, emit=False)
        except TypeError:
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
    if not bool(enabled):
        try:
            import logging
            import traceback

            from shared.debug_flags import env_flag as _env_flag

            _lg = logging.getLogger("ImproveImgSLI")
            if _env_flag("IMGSLI_LASER_DEBUG") or _lg.isEnabledFor(logging.DEBUG):
                prefix = "[laser-debug]"
                stack = "".join(traceback.format_stack(limit=15)[:-1])
                msg = "_toggle_active_magnifier_laser(enabled=False) presenter=%s"
                args = (type(presenter).__name__,)
                if _env_flag("IMGSLI_LASER_DEBUG"):
                    _lg.warning("%s LASER DISABLE [%s]\n%s", prefix, msg % args, stack)
                else:
                    _lg.debug("%s LASER DISABLE [%s]\n%s", prefix, msg % args, stack)
        except Exception:
            pass
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


def _resolve_laser_underline_qcolor(presenter, fallback_state) -> object:
    # Underline must match what the canvas actually draws (feature.py:58
    # `guides_color or guides_state.color`): per active magnifier guides_color
    # if present, else global guides_state.color. Previously only the global
    # was used, so auto-palette instances (store.py:_apply_auto_instance_color)
    # showed white underline while the laser rendered yellow/blue.
    source = "fallback"
    col = None
    try:
        active_cmd = registry().get_feature_command_by_alias("overlay.active_state")
        if active_cmd is not None:
            active_state = active_cmd(presenter.store)
            if active_state is not None:
                col = active_state.get("guides_color")
                if col is not None and hasattr(col, "r"):
                    source = "active_magnifier"
                    q = ensure_visible_qcolor(col)
                    _laser_trace_underline(source, col, q)
                    return q
    except Exception:
        pass
    q = ensure_visible_qcolor(fallback_state.color)
    _laser_trace_underline(f"{source}:global", fallback_state.color, q)
    return q


def _laser_trace_underline(source: str, raw_col, qcolor) -> None:
    try:
        import logging

        from shared.debug_flags import env_flag as _env_flag

        _lg = logging.getLogger("ImproveImgSLI")
        if not (_env_flag("IMGSLI_LASER_DEBUG") or _lg.isEnabledFor(logging.DEBUG)):
            return
        prefix = "[laser-debug]"
        msg = "underline resolve source=%s raw=%r -> QColor(r=%s,g=%s,b=%s,a=%s)"
        args = (source, raw_col, qcolor.red(), qcolor.green(), qcolor.blue(), qcolor.alpha())
        if _env_flag("IMGSLI_LASER_DEBUG"):
            _lg.warning("%s %s", prefix, msg % args)
        else:
            _lg.debug("%s %s", prefix, msg % args)
    except Exception:
        pass


def sync_guides_toolbar_state(presenter) -> None:
    try:
        import logging

        from shared.debug_flags import env_flag as _env_flag

        _lg = logging.getLogger("ImproveImgSLI")
        if _env_flag("IMGSLI_LASER_DEBUG") or _lg.isEnabledFor(logging.DEBUG):
            prefix = "[laser-debug]"
            msg = "sync_guides_toolbar_state called state.enabled=%s thickness=%s color=%r"
            args = (
                getattr(get_guides_widget_state(presenter.store.viewport.view_state), "enabled", None),
                getattr(get_guides_widget_state(presenter.store.viewport.view_state), "thickness", None),
                getattr(get_guides_widget_state(presenter.store.viewport.view_state), "color", None),
            )
            if _env_flag("IMGSLI_LASER_DEBUG"):
                _lg.warning("%s %s", prefix, msg % args)
            else:
                _lg.debug("%s %s", prefix, msg % args)
    except Exception:
        pass
    state = get_guides_widget_state(presenter.store.viewport.view_state)
    ui = getattr(presenter, "widget", None)

    resolved_qcolor = _resolve_laser_underline_qcolor(presenter, state)

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
        btn_guides.setUnderlineColor(resolved_qcolor)
    set_checked_quietly(
        getattr(ui, "btn_magnifier_guides_simple", None), bool(state.enabled)
    )
    btn_guides_width = getattr(ui, "btn_magnifier_guides_width", None)
    if btn_guides_width is not None:
        set_slider_value_quietly(btn_guides_width, int(state.thickness))
        btn_guides_width.setUnderlineColor(resolved_qcolor)


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
