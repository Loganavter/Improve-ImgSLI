from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

@dataclass(slots=True)
class SettingsDialogContext:
    current_language: str
    current_theme: str
    current_max_length: int
    min_limit: int
    max_limit: int
    debug_mode_enabled: bool
    system_notifications_enabled: bool
    current_resolution_limit: int
    tr_func: Callable
    current_ui_font_mode: str = "builtin"
    current_ui_font_family: str = ""
    current_ui_mode: str = "beginner"
    optimize_magnifier_movement: bool = True
    movement_interpolation_method: str = "BILINEAR"
    optimize_laser_smoothing: bool = False
    interpolation_method: str = "LANCZOS"
    zoom_interpolation_method: str = "BILINEAR"
    auto_calculate_psnr: bool = False
    auto_calculate_ssim: bool = False
    auto_crop_black_borders: bool = True
    current_video_fps: int = 60
    store: object | None = None
