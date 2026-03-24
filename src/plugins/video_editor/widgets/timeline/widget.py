import logging
import math
from typing import Any

from PyQt6.QtCore import QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPixmap, QResizeEvent
from PyQt6.QtWidgets import QSizePolicy, QWidget

from shared_toolkit.ui.managers.theme_manager import ThemeManager
from shared_toolkit.ui.widgets.atomic.minimalist_scrollbar import MinimalistScrollBar
from . import interaction as timeline_interaction
from . import layout as timeline_layout
from . import primitives as timeline_primitives
from . import render as timeline_render
from . import theme as timeline_theme
from . import viewport as timeline_viewport

logger = logging.getLogger("ImproveImgSLI")

class VideoTimelineWidget(QWidget):
    headMoved = pyqtSignal(int)
    deletePressed = pyqtSignal()
    zoomChanged = pyqtSignal()
    viewportChanged = pyqtSignal()
    resized = pyqtSignal()

    def __init__(self, snapshots=None, parent=None, store=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self.setMinimumHeight(120)
        self.setSizePolicy(
            QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Preferred
        )
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._lerp_factor = 0.5
        self._visual_index = 0.0
        self._scrub_visual_index: float | None = None
        self._timeline_model = None
        self._row_layout = []
        self._hover_points = []
        self._hover_tooltip_text = None
        self._hover_tooltip_pos = None
        self._collapsed_group_ids: set[str] = set()

        self._lerp_timer = QTimer(self)
        self._tooltip_timer = QTimer(self)
        self._tooltip_timer.setSingleShot(True)
        self._tooltip_timer.setInterval(350)
        self._tooltip_timer.timeout.connect(self._show_hover_tooltip)
        self._v_scrollbar = MinimalistScrollBar(Qt.Orientation.Vertical, self)
        self._v_scrollbar.setVisible(False)
        self._v_scrollbar.valueChanged.connect(lambda _value: self.update())

        fps = 60
        if store and hasattr(store, "settings"):
            fps = getattr(store.settings, "video_recording_fps", 60)
        self._fps = max(1, int(fps))
        interval = int(1000 / max(1, fps))
        self._lerp_timer.setInterval(interval)
        self._lerp_timer.timeout.connect(self._process_lerp)

        self.RULER_HEIGHT = 25
        self.STRIP_HEIGHT = 72
        self.LEFT_GUTTER = 180
        self.MIN_LEFT_GUTTER = 140
        self.MAX_LEFT_GUTTER = 320
        self.GUTTER_RESIZE_MARGIN = 6
        self.GROUP_HEADER_HEIGHT = 20
        self.TRACK_ROW_HEIGHT = 30
        self.CHANNEL_ROW_HEIGHT = 28
        self.BOTTOM_PADDING = 10
        self.SCROLLBAR_STRIP_HEIGHT = 14
        self.HANDLE_SIZE = 18
        self.HEAD_LINE_WIDTH = 2
        self.HANDLE_WIDTH = 14
        self.HANDLE_HEIGHT = 10

        self._zoom_level = 1.0
        self._last_min_zoom = 1.0

        self._snapshots = snapshots if snapshots else []
        self._duration = (
            float(self._snapshots[-1].timestamp) if self._snapshots else 0.0
        )
        self._thumbnails = {}
        self._thumb_indices = []

        self._total_frames = timeline_viewport.compute_total_frames(self)
        self._current_index = 0

        self._anchor_index = 0
        self._drag_index = 0
        self._is_selecting = False
        self._has_selection = False

        self._mouse_down = False
        self._press_pos = None
        self._press_frame = 0
        self._drag_threshold_px = 3
        self._is_resizing_gutter = False

        self._sb_dragging = False
        self._sb_drag_start_x = 0.0
        self._sb_drag_start_value = 0
        self._host_h_scrollbar = None

        self.theme_manager = ThemeManager.get_instance()

        if self.has_snapshots():
            QTimer.singleShot(0, self.fit_view)

    _PROMINENT_TRACK_IDS = {
        "splitter.main.position",
    }

    def showEvent(self, event):
        super().showEvent(event)
        self._bind_host_scrollbar()
        QTimer.singleShot(50, self.fit_view)

    def resizeEvent(self, event: QResizeEvent):
        super().resizeEvent(event)
        self._update_vertical_scrollbar()

        if not self.has_snapshots():
            return

        old_size = event.oldSize()
        if old_size.isValid() and old_size.width() == event.size().width():
            self.update()
            self.resized.emit()
            return

        old_min_zoom = self._last_min_zoom
        new_min_zoom = timeline_viewport.calculate_min_zoom(self)
        is_fitted = (
            math.isclose(self._zoom_level, old_min_zoom, rel_tol=0.05)
            or self._zoom_level < new_min_zoom
        )

        if is_fitted:
            self._zoom_level = new_min_zoom

        self._last_min_zoom = new_min_zoom
        timeline_viewport.update_fixed_width(self)
        self.resized.emit()

    def _update_vertical_scrollbar(self) -> None:
        timeline_viewport.update_vertical_scrollbar(self)

    def _bind_host_scrollbar(self) -> None:
        scroll_area = timeline_viewport.get_scroll_area(self)
        if scroll_area is None:
            return
        scrollbar = scroll_area.horizontalScrollBar()
        if scrollbar is self._host_h_scrollbar:
            return
        if self._host_h_scrollbar is not None:
            try:
                self._host_h_scrollbar.valueChanged.disconnect(
                    self._on_host_horizontal_scroll
                )
                self._host_h_scrollbar.rangeChanged.disconnect(
                    self._on_host_horizontal_scroll_range
                )
            except TypeError:
                pass
        self._host_h_scrollbar = scrollbar
        self._host_h_scrollbar.valueChanged.connect(self._on_host_horizontal_scroll)
        self._host_h_scrollbar.rangeChanged.connect(
            self._on_host_horizontal_scroll_range
        )

    def _on_host_horizontal_scroll(self, _value: int) -> None:
        self._update_vertical_scrollbar()
        self.update()

    def _on_host_horizontal_scroll_range(self, _min_value: int, _max_value: int) -> None:
        self._update_vertical_scrollbar()
        self.update()

    def _rebuild_row_layout(self):
        timeline_layout.rebuild_row_layout(self)

    def _group_key(self, group) -> str:
        return str(getattr(group, "id", getattr(group, "label", "")))

    def _is_group_collapsed(self, group) -> bool:
        return self._group_key(group) in self._collapsed_group_ids

    def _toggle_group_collapsed(self, group) -> None:
        group_key = self._group_key(group)
        if group_key in self._collapsed_group_ids:
            self._collapsed_group_ids.remove(group_key)
        else:
            self._collapsed_group_ids.add(group_key)
        self._rebuild_row_layout()
        self._ensure_preferred_height()
        self.update()

    def _group_accent_color(self, group) -> QColor:
        for track in group.tracks.values():
            visible_channels = self._visible_channels(track)
            if visible_channels:
                return timeline_theme.track_color(self, track.kind, visible_channels[0].kind)
        return QColor(self.theme_manager.get_color("accent"))

    def _group_header_rect(self, left: float, top: float) -> QRectF:
        return QRectF(left, top, self.LEFT_GUTTER, self.GROUP_HEADER_HEIGHT)

    def _group_chevron_rect(self, header_rect: QRectF) -> QRectF:
        return QRectF(header_rect.left() + 8, header_rect.top() + 2, 18, header_rect.height() - 4)

    def _group_toggle_hit(self, pos) -> Any | None:
        return timeline_layout.group_toggle_hit(self, pos)

    def _visible_channels(self, track):
        return timeline_layout.visible_channels(self, track)

    def _channel_has_changes(self, channel) -> bool:
        return timeline_layout.channel_has_changes(channel)

    def _should_show_track(self, track) -> bool:
        return timeline_layout.should_show_track(self, track)

    def _rows_height(self):
        return timeline_layout.rows_height(self)

    def _ensure_preferred_height(self):
        timeline_layout.ensure_preferred_height(self)

    def _update_hover_tooltip(self, pos) -> None:
        timeline_viewport.update_hover_tooltip(self, pos)

    def _show_hover_tooltip(self) -> None:
        timeline_viewport.show_hover_tooltip(self)

    def _is_on_gutter_handle(self, x: int) -> bool:
        return timeline_viewport.is_on_gutter_handle(self, x)

    def set_data(
        self,
        snapshots,
        fps: int | None = None,
        timeline_model=None,
        duration: float | None = None,
    ):
        self._bind_host_scrollbar()
        self._snapshots = list(snapshots or [])
        self._duration = (
            float(duration)
            if duration is not None
            else (float(self._snapshots[-1].timestamp) if self._snapshots else 0.0)
        )
        self._timeline_model = timeline_model
        if fps is not None:
            self._fps = max(1, int(fps))
            self._lerp_timer.setInterval(int(1000 / self._fps))
        self._total_frames = timeline_viewport.compute_total_frames(self)
        self._rebuild_row_layout()
        self._ensure_preferred_height()

        self._anchor_index = 0
        self._drag_index = 0
        self._has_selection = False
        self._is_selecting = False
        self._mouse_down = False
        self._press_pos = None
        self._press_frame = 0
        self._visual_index = 0.0
        self._current_index = 0

        QTimer.singleShot(0, self.fit_view)

    def set_thumbnails(self, thumbnails: dict):
        old_min_zoom = (
            timeline_viewport.calculate_min_zoom(self)
            if self.has_snapshots()
            else self._last_min_zoom
        )
        was_fitted = math.isclose(self._zoom_level, old_min_zoom, rel_tol=0.05)
        self._thumbnails.update(thumbnails)
        self._thumb_indices = sorted(self._thumbnails.keys())
        if self.has_snapshots():
            new_min_zoom = timeline_viewport.calculate_min_zoom(self)
            if was_fitted or self._zoom_level < new_min_zoom:
                self._zoom_level = new_min_zoom
                self._last_min_zoom = new_min_zoom
                timeline_viewport.update_fixed_width(self)
        self.update()

    def add_thumbnail(self, index: int, pixmap: QPixmap):
        old_min_zoom = (
            timeline_viewport.calculate_min_zoom(self)
            if self.has_snapshots()
            else self._last_min_zoom
        )
        was_fitted = math.isclose(self._zoom_level, old_min_zoom, rel_tol=0.05)
        self._thumbnails[index] = pixmap
        if not self._thumb_indices or index > self._thumb_indices[-1]:
            self._thumb_indices.append(index)
        elif index not in self._thumb_indices:
            self._thumb_indices.append(index)
            self._thumb_indices.sort()
        if self.has_snapshots():
            new_min_zoom = timeline_viewport.calculate_min_zoom(self)
            if was_fitted or self._zoom_level < new_min_zoom:
                self._zoom_level = new_min_zoom
                self._last_min_zoom = new_min_zoom
                timeline_viewport.update_fixed_width(self)
        self.update()

    def clear_thumbnails(self):
        self._thumbnails.clear()
        self._thumb_indices.clear()
        self.update()

    def has_snapshots(self) -> bool:
        return self._duration > 0.0 or bool(self._snapshots)

    def get_total_duration(self) -> float:
        return max(0.0, float(self._duration))

    def get_pixels_per_second(self):
        if self._total_frames <= 0:
            return 50.0
        duration = self.get_total_duration()
        if duration <= 0:
            return 50.0
        return timeline_viewport.get_logical_width(self) / duration

    def fit_view(self):
        timeline_viewport.fit_view(self)

    def update_layout_width(self):
        timeline_viewport.update_fixed_width(self)

    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta == 0:
                return

            scroll_area = timeline_viewport.get_scroll_area(self)

            factor = 1.15
            new_zoom = self._zoom_level * factor if delta > 0 else self._zoom_level / factor
            min_zoom = timeline_viewport.calculate_min_zoom(self)
            max_zoom = 1.0
            self._zoom_level = max(min_zoom, min(new_zoom, max_zoom))

            if math.isclose(self._zoom_level, min_zoom, rel_tol=0.01):
                self._zoom_level = min_zoom
                self._last_min_zoom = min_zoom

            timeline_viewport.update_fixed_width(self)

            if scroll_area:
                scrollbar = scroll_area.horizontalScrollBar()
                viewport_width = scroll_area.viewport().width()
                head_x = timeline_viewport.visual_pos_from_index(self, self._visual_index)
                target_scroll = int(round(head_x - (viewport_width / 2.0)))
                target_scroll = max(scrollbar.minimum(), min(target_scroll, scrollbar.maximum()))
                QTimer.singleShot(0, lambda: scrollbar.setValue(target_scroll))

            self.zoomChanged.emit()
            self.viewportChanged.emit()
            event.accept()
        else:
            delta = event.angleDelta().y()
            if delta != 0 and self._v_scrollbar.isVisible():
                direction = -1 if delta > 0 else 1
                self._v_scrollbar.setValue(
                    self._v_scrollbar.value() + direction * self._v_scrollbar.singleStep()
                )
                event.accept()
            else:
                super().wheelEvent(event)
            self.viewportChanged.emit()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        timeline_render.paint_timeline(self, painter, event)
        painter.end()

    def mousePressEvent(self, event):
        timeline_interaction.mouse_press_event(self, event)

    def mouseMoveEvent(self, event):
        timeline_interaction.mouse_move_event(self, event)

    def leaveEvent(self, event):
        timeline_interaction.leave_event(self, event)
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event):
        timeline_interaction.mouse_release_event(self, event)

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
