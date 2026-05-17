from __future__ import annotations

from ..state import get_magnifier_widget_state
from .shared import (
    get_viewport_ctrl,
    show_magnifier_border_color_picker,
    show_magnifier_divider_color_picker,
    trigger_toolbar_binding,
)

def toggle_magnifier_divider_visibility(actions, visible: bool) -> None:
    visible = bool(visible)
    settings = getattr(actions, "settings", None)
    if settings is not None and hasattr(settings, "execute_canvas_feature_command"):
        settings.execute_canvas_feature_command(
            "magnifier",
            "settings.toggle_divider_visibility",
            visible,
        )
        return
    store = getattr(actions, "store", None)
    viewport = getattr(store, "viewport", None) if store is not None else None
    if viewport is None:
        return
    from ..store import active_magnifier_id, update_magnifier_model

    state = get_magnifier_widget_state(viewport.view_state)
    state.default_divider_visible = visible
    update_magnifier_model(
        viewport.view_state,
        viewport.render_config,
        active_magnifier_id(viewport.view_state) or "default",
        divider_visible=visible,
    )
    store.invalidate_render_cache()
    store.emit_state_change()

def set_magnifier_divider_thickness(actions, thickness: int) -> None:
    thickness = max(0, min(10, int(thickness)))
    settings = getattr(actions, "settings", None)
    if settings is not None and hasattr(settings, "execute_canvas_feature_command"):
        settings.execute_canvas_feature_command(
            "magnifier",
            "settings.set_divider_thickness",
            thickness,
        )
        return
    store = getattr(actions, "store", None)
    viewport = getattr(store, "viewport", None) if store is not None else None
    if viewport is None:
        return
    from ..store import active_magnifier_id, update_magnifier_model

    state = get_magnifier_widget_state(viewport.view_state)
    state.default_divider_thickness = thickness
    state.default_divider_visible = thickness > 0
    update_magnifier_model(
        viewport.view_state,
        viewport.render_config,
        active_magnifier_id(viewport.view_state) or "default",
        divider_thickness=thickness,
        divider_visible=thickness > 0,
    )
    store.invalidate_render_cache()
    store.emit_state_change()

def magnifier_toggle_handler(presenter, checked: bool) -> None:
    from plugins.viewport.events import ViewportToggleMagnifierEvent

    event_bus = getattr(presenter, "event_bus", None)
    if event_bus is not None:
        event_bus.emit(ViewportToggleMagnifierEvent(checked))
        return
    viewport_ctrl = get_viewport_ctrl(presenter)
    if viewport_ctrl is not None:
        viewport_ctrl.toggle_magnifier(checked)

def magnifier_toggle_right_click_handler(presenter) -> None:
    from ..store import active_or_default_divider_visible

    visible = not active_or_default_divider_visible(presenter.store.viewport.view_state)
    trigger_toolbar_binding(
        "magnifier.divider.visibility",
        presenter,
        "on_toggled",
        not visible,
    )

def magnifier_orientation_toggle_handler(presenter, checked: bool) -> None:
    from plugins.viewport.events import ViewportToggleMagnifierOrientationEvent

    event_bus = getattr(presenter, "event_bus", None)
    if event_bus is not None:
        event_bus.emit(ViewportToggleMagnifierOrientationEvent(checked))
        return
    viewport_ctrl = get_viewport_ctrl(presenter)
    if viewport_ctrl is not None:
        viewport_ctrl.toggle_magnifier_orientation(checked)

def magnifier_orientation_right_click_handler(presenter) -> None:
    current_mode = getattr(presenter.store.settings, "ui_mode", "beginner")
    if current_mode == "advanced":
        do_toggle_magnifier_orientation(presenter)
        return
    trigger_toolbar_binding(
        "magnifier.divider.thickness",
        presenter,
        "on_right_clicked",
    )

def magnifier_orientation_middle_click_handler(presenter) -> None:
    current_mode = getattr(presenter.store.settings, "ui_mode", "beginner")
    if current_mode != "expert":
        return

    button = presenter.ui.btn_magnifier_orientation
    current_value = button.get_value()
    if current_value == 0:
        saved_value = button.restore_saved_value()
        target_value = (
            saved_value if (saved_value is not None and saved_value > 0) else 3
        )
        button.blockSignals(True)
        button.set_value(target_value)
        button.blockSignals(False)
        trigger_toolbar_binding(
            "magnifier.divider.thickness",
            presenter,
            "on_value_changed",
            target_value,
        )
        return

    button.set_saved_value(current_value)
    button.blockSignals(True)
    button.set_value(0)
    button.blockSignals(False)
    trigger_toolbar_binding(
        "magnifier.divider.thickness",
        presenter,
        "on_value_changed",
        0,
    )

def magnifier_freeze_handler(presenter, checked: bool) -> None:
    from plugins.viewport.events import ViewportToggleFreezeMagnifierEvent

    event_bus = getattr(presenter, "event_bus", None)
    if event_bus is not None:
        event_bus.emit(ViewportToggleFreezeMagnifierEvent(checked))
        return
    viewport_ctrl = get_viewport_ctrl(presenter)
    if viewport_ctrl is not None:
        viewport_ctrl.toggle_freeze_magnifier(checked)

def magnifier_size_handler(presenter, value: int) -> None:
    from plugins.viewport.events import ViewportUpdateMagnifierSizeRelativeEvent

    event_bus = getattr(presenter, "event_bus", None)
    if event_bus is not None:
        event_bus.emit(ViewportUpdateMagnifierSizeRelativeEvent(value / 1000.0))
        return
    viewport_ctrl = get_viewport_ctrl(presenter)
    if viewport_ctrl is not None:
        viewport_ctrl.update_magnifier_size_relative(value / 1000.0)

def magnifier_size_pressed_handler(presenter) -> None:
    from plugins.viewport.events import ViewportOnSliderPressedEvent

    event_bus = getattr(presenter, "event_bus", None)
    if event_bus is not None:
        event_bus.emit(ViewportOnSliderPressedEvent("magnifier_size"))

def magnifier_size_released_handler(presenter) -> None:
    from plugins.viewport.events import ViewportOnSliderReleasedEvent
    from ..store import MagnifierStoreService, default_magnifier_size

    event_bus = getattr(presenter, "event_bus", None)
    if event_bus is None:
        return
    event_bus.emit(
        ViewportOnSliderReleasedEvent(
            "magnifier_size_relative",
            lambda: (
                MagnifierStoreService(presenter.store)
                .get_active_or_first_magnifier()
                .size_relative
                if MagnifierStoreService(presenter.store).get_active_or_first_magnifier()
                is not None
                else default_magnifier_size(presenter.store.viewport.view_state)
            ),
        )
    )

def magnifier_instances_add_handler(presenter) -> None:
    viewport_ctrl = get_viewport_ctrl(presenter)
    if viewport_ctrl is not None:
        viewport_ctrl.add_magnifier()

def magnifier_instances_remove_handler(presenter) -> None:
    viewport_ctrl = get_viewport_ctrl(presenter)
    if viewport_ctrl is not None:
        viewport_ctrl.remove_active_magnifier()

def do_toggle_magnifier_orientation(presenter) -> None:
    from plugins.viewport.events import ViewportToggleMagnifierOrientationEvent
    from ..store import MagnifierStoreService

    model = MagnifierStoreService(presenter.store).get_active_or_first_magnifier()
    current_orientation = bool(model.is_horizontal) if model is not None else False
    new_value = not current_orientation
    event_bus = getattr(presenter, "event_bus", None)
    if event_bus is not None:
        event_bus.emit(ViewportToggleMagnifierOrientationEvent(new_value))
    else:
        viewport_ctrl = get_viewport_ctrl(presenter)
        if viewport_ctrl is not None:
            viewport_ctrl.toggle_magnifier_orientation(new_value)

__all__ = [
    "do_toggle_magnifier_orientation",
    "magnifier_freeze_handler",
    "magnifier_instances_add_handler",
    "magnifier_instances_remove_handler",
    "magnifier_orientation_middle_click_handler",
    "magnifier_orientation_right_click_handler",
    "magnifier_orientation_toggle_handler",
    "magnifier_size_handler",
    "magnifier_size_pressed_handler",
    "magnifier_size_released_handler",
    "magnifier_toggle_handler",
    "magnifier_toggle_right_click_handler",
    "set_magnifier_divider_thickness",
    "show_magnifier_border_color_picker",
    "show_magnifier_divider_color_picker",
    "toggle_magnifier_divider_visibility",
]
