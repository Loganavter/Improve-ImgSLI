from __future__ import annotations

from dataclasses import dataclass, field

from PySide6.QtCore import QPoint, QPointF
from PySide6.QtGui import QColor, QPixmap

@dataclass(slots=True)
class MagnifierRuntimeState:
    _magnifier_pixmap: QPixmap | None = None
    _magnifier_top_left: QPoint | None = None
    _magnifier_centers: list[QPointF] = field(default_factory=list)
    _magnifier_radius: float = 0.0
    _magnifier_border_color: QColor = field(
        default_factory=lambda: QColor(255, 255, 255, 248)
    )
    _magnifier_border_width: float = 2.0
    _mag_quads: list = field(default_factory=list)
    _mag_use_circle_mask: list[bool] = field(default_factory=list)
    _mag_combined_params: list = field(default_factory=list)
    _mag_gpu_active: bool = False
    _mag_gpu_slots: list = field(default_factory=list)
    _mag_gpu_channel_mode: int = 0
    _mag_gpu_diff_mode: int = 0
    _mag_gpu_diff_threshold: float = 20.0 / 255.0
    _mag_gpu_interp_mode: int = 1
    _mag_gpu_widget_geometry_sig: tuple | None = None
