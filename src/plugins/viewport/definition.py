from __future__ import annotations

from core.plugin_system import (
    CommandRegistration,
    PluginDefinition,
    StateSliceRegistration,
)

def build_plugin_definition() -> PluginDefinition:
    return PluginDefinition(
        id="viewport",
        state_slices=(
            StateSliceRegistration(
                key="plugins.viewport",
                metadata={
                    "owner": "plugins.viewport",
                    "description": "Viewport plugin-owned state slice.",
                },
            ),
        ),
        commands=(
            CommandRegistration("viewport.set_split_position"),
            CommandRegistration("viewport.toggle_orientation"),
            CommandRegistration("viewport.update_magnifier_size"),
            CommandRegistration("viewport.update_capture_size"),
            CommandRegistration("viewport.update_movement_speed"),
            CommandRegistration("viewport.set_magnifier_position"),
            CommandRegistration("viewport.set_magnifier_internal_split"),
            CommandRegistration("viewport.toggle_magnifier_part"),
            CommandRegistration("viewport.toggle_magnifier_laser"),
            CommandRegistration("viewport.update_magnifier_combined_state"),
            CommandRegistration("viewport.toggle_magnifier_orientation"),
            CommandRegistration("viewport.toggle_freeze_magnifier"),
            CommandRegistration("viewport.set_magnifier_visibility"),
            CommandRegistration("viewport.toggle_magnifier"),
            CommandRegistration("viewport.slider_pressed"),
            CommandRegistration("viewport.slider_released"),
        ),
        translation_namespaces=(
            "features.magnifier",
            "features.video",
            "ui.tooltips",
            "ui.labels",
            "ui.buttons",
            "settings.general",
        ),
        metadata={
            "scene_owner": True,
            "notes": (
                "Transitional definition. This documents plugin ownership before "
                "full command/state migration out of core."
            ),
        },
    )
