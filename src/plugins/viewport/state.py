from __future__ import annotations

from dataclasses import dataclass, field
from PyQt6.QtCore import QPointF, QPoint, QRect, QByteArray
from typing import Optional, Any

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
    capture_position_relative: QPointF = field(default_factory=lambda: QPointF(0.5, 0.5))
    freeze_magnifier: bool = False
    frozen_capture_point_relative: Optional[QPointF] = None
    magnifier_offset_relative: QPointF = field(default_factory=lambda: QPointF(0.0, 0.0))
    magnifier_spacing_relative: float = 0.05
    magnifier_offset_relative_visual: QPointF = field(default_factory=lambda: QPointF(0.0, 0.0))
    magnifier_spacing_relative_visual: float = 0.05
    magnifier_is_horizontal: bool = False
    magnifier_visible_left: bool = True
    magnifier_visible_center: bool = True
    magnifier_visible_right: bool = True
    magnifier_internal_split: float = 0.5
    magnifier_screen_center: QPoint = field(default_factory=lambda: QPoint())
    magnifier_screen_size: int = 0
    is_magnifier_combined: bool = False
    optimize_magnifier_movement: bool = True

    pixmap_width: int = 0
    pixmap_height: int = 0
    image_display_rect_on_label: QRect = field(default_factory=lambda: QRect())
    fixed_label_width: Optional[int] = None
    fixed_label_height: Optional[int] = None
    resize_in_progress: bool = False

    is_interactive_mode: bool = False
    is_dragging_split_line: bool = False
    is_dragging_capture_point: bool = False
    is_dragging_split_in_magnifier: bool = False
    is_dragging_any_slider: bool = False
    pressed_keys: set[int] = field(default_factory=set)
    space_bar_pressed: bool = False

    showing_single_image_mode: int = 0
    movement_speed_per_sec: float = 2.0
    text_bg_visual_height: float = 0.0
    text_bg_visual_width: float = 0.0

    loaded_geometry: QByteArray = field(default_factory=lambda: QByteArray())
    loaded_was_maximized: bool = False
    loaded_previous_geometry: QByteArray = field(default_factory=lambda: QByteArray())
    loaded_debug_mode_enabled: bool = False

