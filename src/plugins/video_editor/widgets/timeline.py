import math
import logging
import bisect
from PyQt6.QtCore import Qt, pyqtSignal, QRect, QRectF, QPoint, QPointF, QSize, QTimer
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QResizeEvent, QPixmap, QPolygonF
from PyQt6.QtWidgets import QWidget, QScrollArea
from toolkit.managers.theme_manager import ThemeManager

logger = logging.getLogger("ImproveImgSLI")

class VideoTimelineWidget(QWidget):

    headMoved = pyqtSignal(int)
    deletePressed = pyqtSignal()
    zoomChanged = pyqtSignal()
    viewportChanged = pyqtSignal()
    resized = pyqtSignal()

    def __init__(self, snapshots=None, parent=None, store=None):
        super().__init__(parent)
        self.setMinimumHeight(110)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._lerp_factor = 0.5
        self._visual_index = 0.0

        self._lerp_timer = QTimer(self)

        fps = 60
        if store and hasattr(store, 'settings'):
            fps = getattr(store.settings, 'video_recording_fps', 60)
        interval = int(1000 / max(1, fps))
        self._lerp_timer.setInterval(interval)
        self._lerp_timer.timeout.connect(self._process_lerp)

        self.RULER_HEIGHT = 25
        self.HANDLE_SIZE = 18

        self.HEAD_LINE_WIDTH = 2
        self.HANDLE_WIDTH = 14
        self.HANDLE_HEIGHT = 10

        self.MIN_WIDTH_PER_SEC = 50

        self._zoom_level = 1.0

        self._last_min_zoom = 1.0

        self._snapshots = snapshots if snapshots else []
        self._thumbnails = {}
        self._thumb_indices = []

        self._total_frames = len(self._snapshots) if self._snapshots else 0
        self._current_index = 0

        self._anchor_index = 0
        self._drag_index = 0
        self._is_selecting = False
        self._has_selection = False

        self._mouse_down = False
        self._press_pos = None
        self._press_frame = 0
        self._drag_threshold_px = 3

        self.theme_manager = ThemeManager.get_instance()

        if self._snapshots:

            QTimer.singleShot(0, self.fit_view)

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(50, self.fit_view)

    def resizeEvent(self, event: QResizeEvent):
        super().resizeEvent(event)

        if not self._snapshots:
            return

        old_min_zoom = self._last_min_zoom
        new_min_zoom = self._calculate_min_zoom()

        is_fitted = math.isclose(self._zoom_level, old_min_zoom, rel_tol=0.05) or self._zoom_level < new_min_zoom

        if is_fitted:

            self._zoom_level = new_min_zoom

        self._last_min_zoom = new_min_zoom

        self.update_layout_width()

        self.resized.emit()

    def set_data(self, snapshots):
        self._snapshots = snapshots
        self._total_frames = len(snapshots)

        self._anchor_index = 0
        self._drag_index = 0
        self._has_selection = False
        self._is_selecting = False
        self._mouse_down = False
        self._press_pos = None
        self._press_frame = 0

        self._visual_index = 0.0
        self._current_index = 0

        self.fit_view()

    def set_thumbnails(self, thumbnails: dict):
        self._thumbnails.update(thumbnails)
        self._thumb_indices = sorted(self._thumbnails.keys())
        self.update()

    def add_thumbnail(self, index: int, pixmap: QPixmap):
        self._thumbnails[index] = pixmap

        if not self._thumb_indices or index > self._thumb_indices[-1]:
            self._thumb_indices.append(index)
        else:
            if index not in self._thumb_indices:
                self._thumb_indices.append(index)
                self._thumb_indices.sort()
        self.update()

    def clear_thumbnails(self):
        self._thumbnails.clear()
        self._thumb_indices.clear()
        self.update()

    def get_pixels_per_second(self):
        return self.MIN_WIDTH_PER_SEC * self._zoom_level

    def _get_viewport_width(self):
        viewport_width = 800
        parent = self.parent()
        if parent:
            if isinstance(parent, QScrollArea):
                viewport_width = parent.viewport().width()
            elif isinstance(parent, QWidget):

                if isinstance(parent.parent(), QScrollArea):
                    viewport_width = parent.parent().viewport().width()
                else:
                    viewport_width = parent.width()
        return viewport_width

    def _calculate_min_zoom(self):
        if not self._snapshots or self._total_frames <= 0:
            return 0.1

        duration = self._snapshots[-1].timestamp
        if duration <= 0.001:
            return 1.0

        viewport_width = self._get_viewport_width()

        content_width_at_base = duration * self.MIN_WIDTH_PER_SEC

        if content_width_at_base <= 0: return 1.0

        min_zoom = viewport_width / content_width_at_base
        return min_zoom

    def fit_view(self):
        self._zoom_level = self._calculate_min_zoom()
        self._last_min_zoom = self._zoom_level
        self.update_layout_width()
        self.update()

    def update_layout_width(self):
        if not self._snapshots:
            return

        duration = self._snapshots[-1].timestamp
        px_per_sec = self.get_pixels_per_second()

        min_zoom = self._calculate_min_zoom()
        if math.isclose(self._zoom_level, min_zoom, rel_tol=0.01):
            content_width = int(math.floor(duration * px_per_sec))
        else:
            content_width = int(math.ceil(duration * px_per_sec))

        viewport_width = self._get_viewport_width()

        final_width = max(content_width, viewport_width)

        if self.width() != final_width:
            self.setFixedWidth(final_width)
            self.update()

    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta == 0:
                return

            cursor_pos_x_local = event.position().x()

            scroll_area = None
            p = self.parent()
            while p:
                if isinstance(p, QScrollArea):
                    scroll_area = p
                    break
                p = p.parent()

            old_px_per_sec = self.get_pixels_per_second()
            if old_px_per_sec <= 0:
                return

            time_under_cursor = cursor_pos_x_local / old_px_per_sec

            factor = 1.15
            new_zoom = self._zoom_level
            if delta > 0:
                new_zoom *= factor
            else:
                new_zoom /= factor

            min_zoom = self._calculate_min_zoom()
            max_zoom = 500.0

            self._zoom_level = max(min_zoom, min(new_zoom, max_zoom))

            if math.isclose(self._zoom_level, min_zoom, rel_tol=0.01):
                self._zoom_level = min_zoom
                self._last_min_zoom = min_zoom

            self.update_layout_width()

            new_px_per_sec = self.get_pixels_per_second()
            new_cursor_pos_x = time_under_cursor * new_px_per_sec
            diff = new_cursor_pos_x - cursor_pos_x_local

            if scroll_area:
                scrollbar = scroll_area.horizontalScrollBar()
                current_scroll = scrollbar.value()
                target_scroll = int(current_scroll + diff)
                QTimer.singleShot(0, lambda: scrollbar.setValue(target_scroll))

            self.zoomChanged.emit()
            self.viewportChanged.emit()
            event.accept()
        else:
            super().wheelEvent(event)
            self.viewportChanged.emit()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        tm = self.theme_manager
        accent = tm.get_color("accent")
        text_col = tm.get_color("WindowText")
        cursor_color = accent if self._has_selection else text_col

        painter.fillRect(self.rect(), Qt.GlobalColor.transparent)

        if self._total_frames <= 0:
            return

        width = self.width()
        height = self.height()
        content_h = height - self.RULER_HEIGHT

        visible_rect = event.rect()
        start_x = visible_rect.left()
        end_x = visible_rect.right()

        total_dur = self._snapshots[-1].timestamp
        px_per_sec = self.get_pixels_per_second()

        logical_width = total_dur * px_per_sec
        if logical_width < 1.0: logical_width = 1.0

        aspect_ratio = 16/9
        if self._thumb_indices:
            first = self._thumb_indices[0]
            if self._thumbnails.get(first):
                pm = self._thumbnails[first]
                if pm.height() > 0:
                    aspect_ratio = pm.width() / pm.height()

        tile_width = content_h * aspect_ratio

        single_frame_width = logical_width / self._total_frames

        draw_block_width = max(tile_width, single_frame_width)

        first_tile_idx = int(start_x / draw_block_width)
        last_tile_idx = int(end_x / draw_block_width) + 1

        for i in range(first_tile_idx, last_tile_idx + 1):
            block_x_start = i * draw_block_width

            if block_x_start >= logical_width:
                break

            block_center_x = block_x_start + draw_block_width / 2

            frame_idx = self._pos_to_frame(block_center_x)

            thumb_idx = -1
            if self._thumb_indices:
                pos = bisect.bisect_right(self._thumb_indices, frame_idx)
                if pos > 0:
                    thumb_idx = self._thumb_indices[pos - 1]
                else:
                    thumb_idx = self._thumb_indices[0]

            if thumb_idx != -1:
                pix = self._thumbnails.get(thumb_idx)
                if pix:

                    current_width = draw_block_width
                    if block_x_start + current_width > logical_width:
                        current_width = logical_width - block_x_start

                    target_rect = QRectF(block_x_start, 0.0, current_width, float(content_h))
                    source_rect = QRectF(pix.rect())

                    painter.drawPixmap(target_rect, pix, source_rect)

        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        painter.setPen(QPen(text_col, 1))

        step_sec = 100 / px_per_sec
        if step_sec < 0.1: step_sec = 0.1
        elif step_sec < 0.5: step_sec = 0.5
        elif step_sec < 1.0: step_sec = 1.0
        elif step_sec < 2.0: step_sec = 2.0
        elif step_sec < 5.0: step_sec = 5.0
        elif step_sec < 10.0: step_sec = 10.0
        else: step_sec = 30.0

        t = 0.0

        while t <= total_dur:
            x = int(t * px_per_sec)
            if x >= start_x - 50 and x <= end_x + 50:
                painter.setPen(QPen(text_col, 1))
                painter.drawLine(x, content_h, x, content_h + 5)

                if t % (step_sec * 2) < step_sec:
                    painter.drawLine(x, content_h, x, content_h + 12)
                    time_str = self._format_time(t)
                    painter.drawText(x + 4, height - 5, time_str)
            t += step_sec

        painter.setPen(QPen(text_col, 1))
        painter.drawLine(0, content_h, width, content_h)

        if self._has_selection:

            x_anchor = self._frame_to_pos(self._anchor_index)
            x_drag = self._frame_to_pos(self._drag_index)

            x_start = min(x_anchor, x_drag)
            x_end = max(x_anchor, x_drag)

            fill = QColor(accent)
            fill.setAlpha(60)

            painter.fillRect(QRectF(x_start, 0, x_end - x_start, content_h), fill)

            painter.setPen(QPen(accent, 2))

            painter.drawLine(int(x_anchor), 0, int(x_anchor), content_h)

            painter.drawLine(int(x_drag), 0, int(x_drag), content_h)

        x_head = self._visual_pos_from_index(self._visual_index)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        extended_rect = QRectF(-self.HANDLE_WIDTH, -self.HANDLE_HEIGHT - 5,
                               width + 2 * self.HANDLE_WIDTH, height + self.HANDLE_HEIGHT + 5)
        painter.setClipRect(extended_rect, Qt.ClipOperation.ReplaceClip)

        accent_color = self.theme_manager.get_color("accent")
        outline_color = QColor(0, 0, 0, 90)

        line_start_y = 0
        line_end_y = content_h

        painter.setPen(QPen(outline_color, self.HEAD_LINE_WIDTH + 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(QPointF(x_head, line_start_y), QPointF(x_head, line_end_y))

        painter.setPen(QPen(accent_color, self.HEAD_LINE_WIDTH, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(QPointF(x_head, line_start_y), QPointF(x_head, line_end_y))

        handle_poly = [
            QPointF(x_head - self.HANDLE_WIDTH / 2, content_h),
            QPointF(x_head + self.HANDLE_WIDTH / 2, content_h),
            QPointF(x_head, content_h + self.HANDLE_HEIGHT),
        ]

        painter.setPen(QPen(outline_color, 1))
        painter.setBrush(QBrush(accent_color))
        painter.drawPolygon(QPolygonF(handle_poly))

        painter.restore()

    def _format_time(self, seconds):
        m = int(seconds // 60)
        s = int(seconds % 60)
        ms = int((seconds % 1) * 10)
        if m > 0:
            return f"{m}:{s:02d}"
        return f"{s}.{ms}"

    def _pos_to_frame(self, x):
        if self._total_frames <= 0: return 0
        duration = self._snapshots[-1].timestamp
        px_per_sec = self.get_pixels_per_second()
        logical_width = duration * px_per_sec
        if logical_width <= 0: return 0

        ratio = x / logical_width
        frame = int(ratio * self._total_frames)
        return max(0, min(frame, self._total_frames - 1))

    def _frame_to_pos(self, frame):
        if self._total_frames <= 0: return 0
        duration = self._snapshots[-1].timestamp
        px_per_sec = self.get_pixels_per_second()
        logical_width = duration * px_per_sec
        return int((frame / self._total_frames) * logical_width)

    def _visual_pos_from_index(self, float_index):
        if self._total_frames <= 0: return 0.0
        duration = self._snapshots[-1].timestamp
        px_per_sec = self.get_pixels_per_second()
        logical_width = duration * px_per_sec
        return (float_index / self._total_frames) * logical_width

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            x = event.pos().x()
            y = event.pos().y()
            frame = self._pos_to_frame(x)

            self._mouse_down = True
            self._press_pos = event.pos()
            self._press_frame = frame

            current_head_x = self._visual_pos_from_index(self._visual_index)

            handle_hit_width = max(self.HANDLE_WIDTH, self.HANDLE_SIZE) / 2
            handle_hit_height = self.HANDLE_HEIGHT + 5
            hit_handle = (abs(x - current_head_x) <= handle_hit_width) and (y <= handle_hit_height)
            _ = hit_handle

            shift_pressed = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)

            if shift_pressed:

                self._is_selecting = True
                self._has_selection = True
                self._anchor_index = frame
                self._drag_index = frame
            else:

                self._is_selecting = False
                self._has_selection = False
                self._anchor_index = frame
                self._drag_index = frame

            self.set_current_frame(frame)
            self.headMoved.emit(self._current_index)

            self.update()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton:
            frame = self._pos_to_frame(event.pos().x())

            shift_pressed = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            if shift_pressed and not self._is_selecting and self._mouse_down and self._press_pos is not None:
                moved = (event.pos() - self._press_pos).manhattanLength()
                if moved >= self._drag_threshold_px:
                    self._is_selecting = True
                    self._has_selection = True
                    self._anchor_index = self._press_frame
                    self._drag_index = frame

            if self._is_selecting:
                self._drag_index = frame

            self.set_current_frame(frame)

            self.headMoved.emit(self._current_index)
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._mouse_down = False
            self._press_pos = None

        if self._has_selection and self._anchor_index == self._drag_index:
            self._has_selection = False

        self._is_selecting = False
        self.update()

    def get_selection_range(self):
        if not self._has_selection:
            return 0, max(0, self._total_frames - 1)
        return min(self._anchor_index, self._drag_index), max(self._anchor_index, self._drag_index)

    def set_current_frame(self, index):
        self._current_index = max(0, min(index, self._total_frames - 1))

        if abs(self._current_index - self._visual_index) > 2.0:
            self._visual_index = float(self._current_index)

        if not self._lerp_timer.isActive():
            self._lerp_timer.start()

    def _process_lerp(self):
        diff = self._current_index - self._visual_index
        if abs(diff) < 0.01:
            self._visual_index = float(self._current_index)
            self._lerp_timer.stop()
        else:
            self._visual_index += diff * self._lerp_factor
        self.update()

