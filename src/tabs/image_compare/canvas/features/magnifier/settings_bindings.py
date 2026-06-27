from __future__ import annotations

from ui.canvas_infra.scene.widget_contract import CanvasFeatureSettingsEventBinding

from .events import (
    SettingsSetMagnifierBorderColorEvent,
    SettingsSetMagnifierDividerColorEvent,
    SettingsSetMagnifierDividerThicknessEvent,
    SettingsToggleMagnifierDividerVisibilityEvent,
)


def build_magnifier_settings_event_bindings() -> (
    tuple[CanvasFeatureSettingsEventBinding, ...]
):
    return (
        CanvasFeatureSettingsEventBinding(
            event_type=SettingsToggleMagnifierDividerVisibilityEvent,
            command_id="settings.toggle_divider_visibility",
            extract_args=lambda event: (event.visible,),
        ),
        CanvasFeatureSettingsEventBinding(
            event_type=SettingsSetMagnifierDividerColorEvent,
            command_id="settings.set_divider_color",
            extract_args=lambda event: (event.color,),
        ),
        CanvasFeatureSettingsEventBinding(
            event_type=SettingsSetMagnifierDividerThicknessEvent,
            command_id="settings.set_divider_thickness",
            extract_args=lambda event: (event.thickness,),
        ),
        CanvasFeatureSettingsEventBinding(
            event_type=SettingsSetMagnifierBorderColorEvent,
            command_id="settings.set_border_color",
            extract_args=lambda event: (event.color,),
        ),
    )
