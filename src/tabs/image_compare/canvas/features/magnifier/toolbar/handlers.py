from __future__ import annotations

from tabs.image_compare.canvas.features.magnifier.state.feature_state import get_magnifier_widget_state
from tabs.image_compare.canvas.features.magnifier.toolbar.shared import (
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
    from tabs.image_compare.canvas.features.magnifier.state.store import active_magnifier_id, update_magnifier_model

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
    from tabs.image_compare.canvas.features.magnifier.state.store import active_magnifier_id, update_magnifier_model

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
    from ui.canvas_infra.scene.feature_state_api import execute_feature_command

    store = getattr(presenter, "store", None)
    if store is not None:
        execute_feature_command(store, "magnifier", "toggle_enabled", checked)


def magnifier_toggle_right_click_handler(presenter) -> None:
    from tabs.image_compare.canvas.features.magnifier.state.store import active_or_default_divider_visible

    visible = not active_or_default_divider_visible(presenter.store.viewport.view_state)
    trigger_toolbar_binding(
        "magnifier.divider.visibility",
        presenter,
        "on_toggled",
        not visible,
    )


def magnifier_orientation_toggle_handler(presenter, checked: bool) -> None:
    from ui.canvas_infra.scene.feature_state_api import execute_feature_command

    store = getattr(presenter, "store", None)
    if store is not None:
        execute_feature_command(store, "magnifier", "set_active_orientation", checked)


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
        saved_value = button.get_saved_value()
        target_value = (
            saved_value if (saved_value is not None and saved_value > 0) else 3
        )
        button.set_saved_value(None)
        button.blockSignals(True)
        button.set_value(target_value)
        button.blockSignals(False)
        set_magnifier_divider_thickness(presenter, target_value)
    else:
        button.set_saved_value(current_value)
        button.blockSignals(True)
        button.set_value(0)
        button.blockSignals(False)
        set_magnifier_divider_thickness(presenter, 0)


def magnifier_freeze_handler(presenter, checked: bool) -> None:
    from ui.canvas_infra.scene.feature_state_api import execute_feature_command

    store = getattr(presenter, "store", None)
    if store is not None:
        execute_feature_command(store, "magnifier", "set_active_freeze", checked)


def magnifier_size_handler(presenter, value: int) -> None:
    from ui.canvas_infra.scene.feature_state_api import execute_feature_command

    store = getattr(presenter, "store", None)
    if store is not None:
        execute_feature_command(store, "magnifier", "set_active_size", value / 1000.0)


def magnifier_size_pressed_handler(presenter) -> None:

    pass


def magnifier_size_released_handler(presenter) -> None:

    pass


def magnifier_instances_add_handler(presenter) -> None:
    from ui.canvas_infra.scene.feature_state_api import execute_feature_command

    store = getattr(presenter, "store", None)
    if store is not None:
        execute_feature_command(store, "magnifier", "add_instance")


def magnifier_instances_remove_handler(presenter) -> None:
    from ui.canvas_infra.scene.feature_state_api import execute_feature_command

    store = getattr(presenter, "store", None)
    if store is not None:
        execute_feature_command(store, "magnifier", "remove_active_instance")


def do_toggle_magnifier_orientation(presenter) -> None:
    from ui.canvas_infra.scene.feature_state_api import execute_feature_command

    from tabs.image_compare.canvas.features.magnifier.state.store import MagnifierStoreService

    model = MagnifierStoreService(presenter.store).get_active_or_first_magnifier()
    current_orientation = bool(model.is_horizontal) if model is not None else False
    new_value = not current_orientation
    store = getattr(presenter, "store", None)
    if store is not None:
        execute_feature_command(store, "magnifier", "set_active_orientation", new_value)


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
