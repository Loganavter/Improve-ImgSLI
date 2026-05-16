from __future__ import annotations

import math
from dataclasses import dataclass

from PyQt6.QtCore import Qt

from core.constants import AppConstants
from domain.types import Point

from .interactive_movement_math import resolve_axis_direction

@dataclass(frozen=True)
class MovementDirections:
    dx: int = 0
    dy: int = 0
    ds: int = 0

    def as_tuple(self) -> tuple[int, int, int]:
        return (int(self.dx), int(self.dy), int(self.ds))

    def is_zero(self) -> bool:
        return self.dx == 0 and self.dy == 0 and self.ds == 0

def collect_movement_keys(pressed_keys, allowed_keys) -> set[int]:
    return {key for key in pressed_keys if key in allowed_keys}

def resolve_movement_directions(interaction_state, keys) -> MovementDirections:
    return MovementDirections(
        dx=resolve_axis_direction(
            keys,
            interaction_state.last_horizontal_movement_key,
            negative_key=Qt.Key.Key_A,
            positive_key=Qt.Key.Key_D,
        ),
        dy=resolve_axis_direction(
            keys,
            interaction_state.last_vertical_movement_key,
            negative_key=Qt.Key.Key_W,
            positive_key=Qt.Key.Key_S,
        ),
        ds=resolve_axis_direction(
            keys,
            interaction_state.last_spacing_movement_key,
            negative_key=Qt.Key.Key_Q,
            positive_key=Qt.Key.Key_E,
        ),
    )

def compute_speed_factor(view_state) -> float:
    return (
        view_state.movement_speed_per_sec
        * AppConstants.BASE_MOVEMENT_SPEED
    )

def apply_offset_input(current_offset: Point, dirs: MovementDirections, speed_factor: float, delta_time_sec: float) -> tuple[Point, bool]:
    if dirs.dx == 0 and dirs.dy == 0:
        return current_offset, False
    dx_dir = float(dirs.dx)
    dy_dir = float(dirs.dy)
    length = math.sqrt(dx_dir**2 + dy_dir**2)
    if length > 1.0:
        dx_dir /= length
        dy_dir /= length
    delta_x = dx_dir * speed_factor * delta_time_sec
    delta_y = dy_dir * speed_factor * delta_time_sec
    new_offset = Point(current_offset.x + delta_x, current_offset.y + delta_y)
    changed = (
        not math.isclose(new_offset.x, current_offset.x, abs_tol=1e-9)
        or not math.isclose(new_offset.y, current_offset.y, abs_tol=1e-9)
    )
    return new_offset, changed

def apply_spacing_input(current_spacing: float, ds_dir: int, speed_factor: float, delta_time_sec: float, *, min_spacing: float, max_spacing: float) -> tuple[float, bool]:
    delta_spacing = ds_dir * speed_factor * delta_time_sec * 0.35
    new_spacing = current_spacing + delta_spacing
    clamped_spacing = max(min_spacing, min(max_spacing, new_spacing))
    changed = not math.isclose(clamped_spacing, current_spacing, abs_tol=1e-9)
    return clamped_spacing, changed
