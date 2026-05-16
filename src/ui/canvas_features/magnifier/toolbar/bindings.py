from __future__ import annotations

from ui.canvas_infra.scene.widget_contract import CanvasFeatureToolbarBinding

from .handlers import (
    magnifier_freeze_handler,
    magnifier_instances_add_handler,
    magnifier_instances_remove_handler,
    magnifier_orientation_middle_click_handler,
    magnifier_orientation_right_click_handler,
    magnifier_orientation_toggle_handler,
    magnifier_size_handler,
    magnifier_size_pressed_handler,
    magnifier_size_released_handler,
    magnifier_toggle_handler,
    magnifier_toggle_right_click_handler,
    set_magnifier_divider_thickness,
    show_magnifier_border_color_picker,
    show_magnifier_divider_color_picker,
    toggle_magnifier_divider_visibility,
)
from .sync import (
    sync_magnifier_enabled_state,
    sync_magnifier_freeze_state,
    sync_magnifier_orientation_state,
    sync_magnifier_size_state,
    sync_magnifier_toolbar_state,
)

def build_magnifier_toolbar_bindings() -> tuple[CanvasFeatureToolbarBinding, ...]:
    return (
        CanvasFeatureToolbarBinding(
            control_id="magnifier.enabled",
            on_toggled=magnifier_toggle_handler,
            on_right_clicked=magnifier_toggle_right_click_handler,
            sync_state=sync_magnifier_enabled_state,
        ),
        CanvasFeatureToolbarBinding(
            control_id="magnifier.orientation",
            on_toggled=magnifier_orientation_toggle_handler,
            on_right_clicked=magnifier_orientation_right_click_handler,
            on_middle_clicked=magnifier_orientation_middle_click_handler,
            sync_state=sync_magnifier_orientation_state,
        ),
        CanvasFeatureToolbarBinding(
            control_id="magnifier.size",
            on_value_changed=magnifier_size_handler,
            on_pressed=magnifier_size_pressed_handler,
            on_released=magnifier_size_released_handler,
            sync_state=sync_magnifier_size_state,
        ),
        CanvasFeatureToolbarBinding(
            control_id="magnifier.freeze",
            on_toggled=magnifier_freeze_handler,
            sync_state=sync_magnifier_freeze_state,
        ),
        CanvasFeatureToolbarBinding(
            control_id="magnifier.instances.add",
            on_toggled=lambda presenter, _checked: magnifier_instances_add_handler(
                presenter
            ),
        ),
        CanvasFeatureToolbarBinding(
            control_id="magnifier.instances.remove",
            on_toggled=lambda presenter, _checked: magnifier_instances_remove_handler(
                presenter
            ),
        ),
        CanvasFeatureToolbarBinding(
            control_id="magnifier.divider.visibility",
            on_toggled=lambda presenter, checked: toggle_magnifier_divider_visibility(
                presenter,
                not checked,
            ),
            sync_state=sync_magnifier_toolbar_state,
        ),
        CanvasFeatureToolbarBinding(
            control_id="magnifier.divider.thickness",
            on_value_changed=set_magnifier_divider_thickness,
            on_right_clicked=show_magnifier_divider_color_picker,
            sync_state=sync_magnifier_toolbar_state,
        ),
        CanvasFeatureToolbarBinding(
            control_id="magnifier.border.color",
            on_right_clicked=show_magnifier_border_color_picker,
            sync_state=sync_magnifier_toolbar_state,
        ),
    )
