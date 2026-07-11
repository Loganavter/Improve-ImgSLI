from __future__ import annotations

from domain.qt_adapters import qcolor_to_color
from tabs.image_compare.canvas.registry import registry


def set_checked_quietly(control, value: bool) -> None:
    if control is None or control.isChecked() == value:
        return
    control.setChecked(value, emit_signal=False)


def set_slider_value_quietly(control, value: int) -> None:
    if control is None:
        return
    current_value = (
        control.get_value()
        if hasattr(control, "get_value")
        else control.value() if hasattr(control, "value") else None
    )
    if current_value == value:
        return
    control.blockSignals(True)
    try:
        if hasattr(control, "set_value"):
            control.set_value(value)
        else:
            control.setValue(value)
    finally:
        control.blockSignals(False)


def show_canvas_feature_color_picker(
    presenter,
    *,
    key: str,
    setting_key: str,
    title_key: str,
    command_id: str,
    post_apply=None,
) -> None:
    window_presenter = getattr(presenter.main_window_app, "presenter", None)
    if window_presenter is None or not hasattr(window_presenter, "get_feature"):
        return
    settings_presenter = window_presenter.get_feature("settings")
    if settings_presenter is None:
        return

    def _apply_selected(color):
        settings_controller = getattr(
            getattr(presenter, "main_controller", None),
            "settings",
            None,
        )
        if settings_controller is not None:
            settings_controller.execute_canvas_feature_command(
                "magnifier",
                command_id,
                qcolor_to_color(color),
            )

    settings_presenter.show_canvas_feature_color_picker(
        key=key,
        setting_key=setting_key,
        title_key=title_key,
        on_selected=_apply_selected,
        post_apply=post_apply,
    )


def show_magnifier_divider_color_picker(presenter) -> None:
    def _post_apply(color):
        button = getattr(
            getattr(presenter, "ui", None), "btn_magnifier_orientation", None
        )
        if button is not None:
            button.setUnderlineColor(color)

    show_canvas_feature_color_picker(
        presenter,
        key="magnifier_divider",
        setting_key="magnifier.divider.color",
        title_key="ui.choose_magnifier_divider_line_color",
        command_id="settings.set_divider_color",
        post_apply=_post_apply,
    )


def show_magnifier_border_color_picker(presenter) -> None:
    show_canvas_feature_color_picker(
        presenter,
        key="magnifier_border",
        setting_key="magnifier.border.color",
        title_key="ui.choose_magnifier_border_color",
        command_id="settings.set_border_color",
    )


def get_viewport_ctrl(presenter):
    controller = getattr(presenter, "main_controller", None)
    return getattr(controller, "viewport_plugin", None) if controller else None


def trigger_toolbar_binding(control_id: str, presenter, action: str, *args) -> None:
    binding = registry().get_feature_toolbar_binding(control_id)
    callback = getattr(binding, action, None) if binding is not None else None
    if callback is not None:
        callback(presenter, *args)
