from __future__ import annotations

from dataclasses import dataclass

@dataclass(slots=True)
class SettingsDialogData:
    language: str
    theme: str
    max_name_length: int
    debug_enabled: bool
    system_notifications_enabled: bool
    resolution_limit: int
    ui_font_mode: str
    ui_font_family: str
    optimize_magnifier_movement: bool
    magnifier_interpolation_method: str
    optimize_laser_smoothing: bool
    laser_interpolation_method: str
    zoom_interpolation_method: str
    auto_calculate_psnr: bool
    auto_calculate_ssim: bool
    auto_crop_black_borders: bool
    ui_mode: str
    video_recording_fps: int
