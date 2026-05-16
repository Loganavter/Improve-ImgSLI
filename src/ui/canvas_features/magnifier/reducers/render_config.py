from __future__ import annotations

from dataclasses import replace

from core.state_management.action_base import Action
from plugins.viewport.actions import SetMagnifierMovementInterpolationMethodAction

def reduce_magnifier_render_config(config, action: Action):
    if isinstance(action, SetMagnifierMovementInterpolationMethodAction):
        return replace(
            config,
            interactive_movement_interpolation_method=action.method,
            movement_interpolation_method=action.method,
        )
    return config
