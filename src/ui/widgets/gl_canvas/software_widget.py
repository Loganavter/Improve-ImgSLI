from __future__ import annotations

import logging

from PyQt6.QtCore import QPoint, QPointF, QRect, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen, QPixmap

from shared_toolkit.ui.widgets.atomic.clickable_label import ClickableLabel

logger = logging.getLogger("ImproveImgSLI")

class SoftwareCanvas(ClickableLabel):
    supports_legacy_gl_magnifier = True
    uses_quick_canvas_overlay = False

    zoomChanged = pyqtSignal(float)
    pasteOverlayDirectionSelected = pyqtSignal(str)
    pasteOverlayCancelled = pyqtSignal()
    firstFrameRendered = pyqtSignal()
    firstVisualFrameReady = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._store = None
        self._render_scene = None
        self._split_position_sync = None
        self._base_pixmap: QPixmap | None = None
        self._magnifier_pixmap: QPixmap | None = None
        self._magnifier_top_left: QPoint | None = None
        self._capture_center: QPointF | None = None
        self._capture_radius: float = 0.0
        self._magnifier_centers: list[QPointF] = []
        self._magnifier_radius: float = 0.0
        self._show_guides = False
        self._laser_color = QColor(255, 255, 255, 120)
        self._guides_thickness = 1
        self._show_divider = False
        self._split_pos = 0
        self._is_horizontal_split = False
        self._divider_color = QColor(255, 255, 255, 255)
        self._divider_thickness = 2
        self._capture_color = QColor(255, 50, 100, 230)
        self._drag_overlay_visible = False
        self._drag_overlay_horizontal = False
        self._drag_overlay_texts = ("", "")
        self._paste_overlay_visible = False
        self._paste_overlay_horizontal = False
        self._paste_overlay_texts = {"up": "", "down": "", "left": "", "right": ""}
        self._paste_overlay_hovered_button = None
        self.zoom_level = 1.0
        self.pan_offset_x = 0.0
        self.pan_offset_y = 0.0
        self.split_position = 0.5
        self.display_split_position = 0.5
        self.is_horizontal = False
        self._first_frame_rendered_emitted = False
        self._update_batch_depth = 0
        self._update_pending = False

    def set_store(self, store):
        self._store = store

    def set_render_scene(self, scene):
        self._render_scene = scene

    def set_split_position_sync(self, sync_callback):
        self._split_position_sync = sync_callback

    def set_apply_channel_mode_in_shader(self, enabled: bool):
        return None

    def begin_update_batch(self):
        self._update_batch_depth += 1

    def end_update_batch(self):
        self._update_batch_depth = max(0, self._update_batch_depth - 1)
        if self._update_batch_depth == 0 and self._update_pending:
            self._update_pending = False
            self.update()

    def _request_update(self):
        if self._update_batch_depth > 0:
            self._update_pending = True
            return
        self.update()

    def _emit_first_frame_rendered(self):
        if self._first_frame_rendered_emitted:
            return
        self._first_frame_rendered_emitted = True
        self.firstFrameRendered.emit()
        self.firstVisualFrameReady.emit()

    def set_layers(
        self,
        background: QPixmap | None,
        magnifier: QPixmap | None,
        mag_pos: QPoint | None,
        coords_snapshot=None,
    ):
        self._base_pixmap = background
        self._magnifier_pixmap = magnifier
        self._magnifier_top_left = mag_pos
        if background is not None and not background.isNull():
            self._emit_first_frame_rendered()
        self._request_update()

    def setPixmap(self, pixmap: QPixmap | None):
        self._base_pixmap = pixmap
        if pixmap is not None and not pixmap.isNull():
            self._emit_first_frame_rendered()
        self._request_update()

    def clear(self):
        self._base_pixmap = None
        self._magnifier_pixmap = None
        self._magnifier_top_left = None
        self._capture_center = None
        self._capture_radius = 0.0
        self._magnifier_centers = []
        self._magnifier_radius = 0.0
        self._show_divider = False
        self._request_update()

    def set_magnifier_content(self, pixmap: QPixmap | None, top_left: QPoint | None):
        self._magnifier_pixmap = pixmap
        self._magnifier_top_left = top_left
        self._request_update()

    def set_overlay_coords(
        self,
        capture_center: QPointF | None,
        capture_radius: float,
        mag_centers: list[QPointF],
        mag_radius: float,
    ):
        self._capture_center = capture_center
        self._capture_radius = float(capture_radius or 0.0)
        self._magnifier_centers = list(mag_centers or [])
        self._magnifier_radius = float(mag_radius or 0.0)
        self._request_update()

    def set_split_line_params(
        self,
        visible: bool,
        pos: int,
        is_horizontal: bool,
        color: QColor,
        thickness: int,
    ):
        self._show_divider = bool(visible)
        self._split_pos = int(pos or 0)
        axis_size = max(1, self.height() if is_horizontal else self.width())
        self.display_split_position = max(0.0, min(1.0, float(pos or 0) / float(axis_size)))
        self._is_horizontal_split = bool(is_horizontal)
        self._divider_color = QColor(color) if color is not None else QColor(255, 255, 255)
        self._divider_thickness = max(1, int(thickness or 1))
        self._request_update()

    def set_guides_params(self, visible: bool, color: QColor, thickness: int):
        self._show_guides = bool(visible)
        self._laser_color = QColor(color) if color is not None else QColor(255, 255, 255, 120)
        self._guides_thickness = max(1, int(thickness or 1))
        self._request_update()

    def set_capture_color(self, color: QColor):
        if color is not None:
            self._capture_color = QColor(color)
            self._request_update()

    def set_capture_area(
        self, center: QPoint | QPointF | None, size: int | float, color: QColor | None = None
    ):
        if color is not None:
            self._capture_color = QColor(color)
        if center is None or not size:
            self._capture_center = None
            self._capture_radius = 0.0
        else:
            self._capture_center = QPointF(float(center.x()), float(center.y()))
            self._capture_radius = float(size) / 2.0
        self._request_update()

    def upload_diff_source_pil_image(self, pil_image):
        return None

    def clear_magnifier_gpu(self):
        self._magnifier_pixmap = None
        self._magnifier_top_left = None
        self._request_update()
        return None

    def set_drag_overlay_state(
        self,
        visible: bool,
        horizontal: bool = False,
        text1: str = "",
        text2: str = "",
    ):
        self._drag_overlay_visible = bool(visible)
        self._drag_overlay_horizontal = bool(horizontal)
        self._drag_overlay_texts = (text1 or "", text2 or "")
        self._request_update()

    def is_drag_overlay_visible(self) -> bool:
        return self._drag_overlay_visible

    def set_paste_overlay_state(
        self,
        visible: bool,
        is_horizontal: bool = False,
        texts: dict | None = None,
    ):
        self._paste_overlay_visible = bool(visible)
        self._paste_overlay_horizontal = bool(is_horizontal)
        if texts is not None:
            self._paste_overlay_texts = {
                "up": texts.get("up", ""),
                "down": texts.get("down", ""),
                "left": texts.get("left", ""),
                "right": texts.get("right", ""),
            }
        if not visible:
            self._paste_overlay_hovered_button = None
        self._request_update()

    def is_paste_overlay_visible(self) -> bool:
        return self._paste_overlay_visible

    def _paste_overlay_button_at(self, pos: QPointF | QPoint) -> str | None:
        return None

    def _set_paste_overlay_hover(self, hovered: str | None):
        self._paste_overlay_hovered_button = hovered
        self._request_update()

    def set_split_pos(self, pos: float):
        self.split_position = float(pos or 0.0)
        if self._split_position_sync is not None:
            try:
                self._split_position_sync(self.split_position)
            except Exception:
                logger.exception("SoftwareCanvas split position sync failed")

    def set_zoom(self, zoom: float):
        self.zoom_level = float(zoom or 1.0)
        self.zoomChanged.emit(self.zoom_level)

    def set_pan(self, x: float, y: float):
        self.pan_offset_x = float(x or 0.0)
        self.pan_offset_y = float(y or 0.0)

    def reset_view(self):
        self.set_zoom(1.0)
        self.set_pan(0.0, 0.0)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        if self._base_pixmap is not None and not self._base_pixmap.isNull():
            painter.drawPixmap(self._aligned_rect(self._base_pixmap), self._base_pixmap)

        if (
            self._magnifier_pixmap is not None
            and not self._magnifier_pixmap.isNull()
            and self._magnifier_top_left is not None
        ):
            painter.drawPixmap(self._magnifier_top_left, self._magnifier_pixmap)

        self._paint_guides(painter)
        self._paint_capture_area(painter)
        self._paint_split_line(painter)
        self._paint_drag_overlay(painter)
        self._paint_paste_overlay(painter)
        painter.end()

    def _aligned_rect(self, pixmap: QPixmap) -> QRect:
        rect = self.contentsRect()
        x = rect.x()
        y = rect.y()
        alignment = self.alignment()
        if alignment & Qt.AlignmentFlag.AlignHCenter:
            x += max(0, (rect.width() - pixmap.width()) // 2)
        elif alignment & Qt.AlignmentFlag.AlignRight:
            x += max(0, rect.width() - pixmap.width())
        if alignment & Qt.AlignmentFlag.AlignVCenter:
            y += max(0, (rect.height() - pixmap.height()) // 2)
        elif alignment & Qt.AlignmentFlag.AlignBottom:
            y += max(0, rect.height() - pixmap.height())
        return QRect(x, y, pixmap.width(), pixmap.height())

    def _paint_guides(self, painter: QPainter):
        if not self._show_guides or self._capture_center is None or not self._magnifier_centers:
            return
        pen = QPen(self._laser_color, float(self._guides_thickness))
        pen.setCosmetic(True)
        painter.setPen(pen)
        for center in self._magnifier_centers:
            painter.drawLine(self._capture_center, center)

    def _paint_capture_area(self, painter: QPainter):
        if self._capture_center is None or self._capture_radius <= 0:
            return
        pen = QPen(self._capture_color, 2.0)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(self._capture_center, self._capture_radius, self._capture_radius)

    def _paint_split_line(self, painter: QPainter):
        if not self._show_divider:
            return
        pen = QPen(self._divider_color, float(self._divider_thickness))
        pen.setCosmetic(True)
        painter.setPen(pen)
        if self._is_horizontal_split:
            painter.drawLine(0, self._split_pos, self.width(), self._split_pos)
        else:
            painter.drawLine(self._split_pos, 0, self._split_pos, self.height())

    def _paint_drag_overlay(self, painter: QPainter):
        if not self._drag_overlay_visible:
            return
        rect = self.rect().adjusted(20, 20, -20, -20)
        painter.fillRect(rect, QColor(0, 0, 0, 96))
        painter.setPen(QColor(255, 255, 255, 220))
        text = "\n".join(part for part in self._drag_overlay_texts if part)
        if text:
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)

    def _paint_paste_overlay(self, painter: QPainter):
        if not self._paste_overlay_visible:
            return
        rect = self.rect().adjusted(30, 30, -30, -30)
        painter.fillRect(rect, QColor(0, 0, 0, 72))
        painter.setPen(QColor(255, 255, 255, 220))
        text = " / ".join(
            value for value in (
                self._paste_overlay_texts.get("up"),
                self._paste_overlay_texts.get("down"),
                self._paste_overlay_texts.get("left"),
                self._paste_overlay_texts.get("right"),
            )
            if value
        )
        if text:
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
