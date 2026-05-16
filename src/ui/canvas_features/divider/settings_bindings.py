from __future__ import annotations

from ui.canvas_infra.scene.widget_contract import CanvasFeatureSettingsEventBinding

from .events import (
    SettingsSetDividerColorEvent,
    SettingsSetDividerThicknessEvent,
    SettingsToggleDividerVisibilityEvent,
)

def build_divider_settings_event_bindings() -> tuple[CanvasFeatureSettingsEventBinding, ...]:
    return (
        CanvasFeatureSettingsEventBinding(
            event_type=SettingsToggleDividerVisibilityEvent,
            command_id="settings.toggle_visibility",
            extract_args=lambda event: (event.visible,),
        ),
        CanvasFeatureSettingsEventBinding(
            event_type=SettingsSetDividerThicknessEvent,
            command_id="settings.set_thickness",
            extract_args=lambda event: (event.thickness,),
        ),
        CanvasFeatureSettingsEventBinding(
            event_type=SettingsSetDividerColorEvent,
            command_id="settings.set_color",
            extract_args=lambda event: (event.color,),
        ),
    )

