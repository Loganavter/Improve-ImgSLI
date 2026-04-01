from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from domain.types import Point, Rect

@dataclass
class ViewportState:

    split_position: float = 0.5
    split_position_visual: float = 0.5
    is_horizontal: bool = False

    use_magnifier: bool = False
    magnifiers: dict[str, Any] = field(default_factory=dict)
    active_magnifier_id: Optional[str] = None
    magnifier_size_relative: float = 0.2
    capture_size_relative: float = 0.1
    capture_position_relative: Point = field(
        default_factory=lambda: Point(0.5, 0.5)
    )
    freeze_magnifier: bool = False
    frozen_capture_point_relative: Optional[Point] = None
    magnifier_offset_relative: Point = field(
        default_factory=lambda: Point(0.0, 0.0)
    )
    magnifier_spacing_relative: float = 0.1
    magnifier_offset_relative_visual: Point = field(
        default_factory=lambda: Point(0.0, 0.0)
    )
    magnifier_spacing_relative_visual: float = 0.1
    magnifier_is_horizontal: bool = False
    magnifier_visible_left: bool = True
    magnifier_visible_center: bool = True
    magnifier_visible_right: bool = True
    magnifier_internal_split: float = 0.5
    magnifier_screen_center: Point = field(default_factory=lambda: Point())
    magnifier_screen_size: int = 0
    is_magnifier_combined: bool = False
    optimize_magnifier_movement: bool = True

    pixmap_width: int = 0
    pixmap_height: int = 0
    image_display_rect_on_label: Rect = field(default_factory=lambda: Rect())
    fixed_label_width: Optional[int] = None
    fixed_label_height: Optional[int] = None
    resize_in_progress: bool = False

    is_interactive_mode: bool = False
    is_dragging_split_line: bool = False
    is_dragging_capture_point: bool = False
    is_dragging_split_in_magnifier: bool = False
    is_dragging_any_slider: bool = False
    interaction_session_id: int = 0
    is_user_interacting: bool = False
    pressed_keys: set[int] = field(default_factory=set)
    last_horizontal_movement_key: int | None = None
    last_vertical_movement_key: int | None = None
    last_spacing_movement_key: int | None = None
    space_bar_pressed: bool = False

    showing_single_image_mode: int = 0
    movement_speed_per_sec: float = 2.0
    text_bg_visual_height: float = 0.0
    text_bg_visual_width: float = 0.0

    loaded_geometry: bytes = b""
    loaded_was_maximized: bool = False
    loaded_previous_geometry: bytes = b""
    loaded_debug_mode_enabled: bool = False
