from __future__ import annotations

from ui.canvas_infra.scene.widget_contract import CanvasFeatureSettingsEventBinding

from .events import (
    SettingsSetGuidesColorEvent,
    SettingsSetGuidesThicknessEvent,
    SettingsToggleGuidesVisibilityEvent,
)

def build_guides_settings_event_bindings() -> tuple[CanvasFeatureSettingsEventBinding, ...]:
    return (
        CanvasFeatureSettingsEventBinding(
            event_type=SettingsToggleGuidesVisibilityEvent,
            command_id="settings.toggle_visibility",
            extract_args=lambda event: (event.enabled,),
        ),
        CanvasFeatureSettingsEventBinding(
            event_type=SettingsSetGuidesThicknessEvent,
            command_id="settings.set_thickness",
            extract_args=lambda event: (event.thickness,),
        ),
        CanvasFeatureSettingsEventBinding(
            event_type=SettingsSetGuidesColorEvent,
            command_id="settings.set_color",
            extract_args=lambda event: (event.color,),
        ),
    )

