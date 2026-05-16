from __future__ import annotations

from dataclasses import replace

from core.state_management.action_base import Action
from plugins.viewport.actions import (
    SetMagnifierScreenCenterAction,
    SetMagnifierScreenSizeAction,
)

def reduce_magnifier_geometry_state(geometry_state, action: Action):
    if isinstance(action, SetMagnifierScreenCenterAction):
        return replace(geometry_state, active_overlay_screen_center=action.center)
    if isinstance(action, SetMagnifierScreenSizeAction):
        return replace(geometry_state, active_overlay_screen_size=action.size)
    return geometry_state
