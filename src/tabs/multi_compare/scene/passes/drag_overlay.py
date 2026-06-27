"""Live drag/drop overlay painter for Multi Compare."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPalette, QPen

from tabs.multi_compare.ui import layout_geometry


class DragDropOverlaySource:
    """Paints live-only drag/drop affordances."""

    DROP_LABEL_FONT_PT = 10

    def should_paint(self, _composition, state) -> bool:
        return bool(state.drag_active)

    def paint(self, painter: QPainter, *, host) -> None:
        leaf_rects = host._leaf_rects()
        if host.state.drag_internal and host.state.drag_source_slot_id is not None:
            self._paint_drag_source(painter, host, leaf_rects)
        self._paint_drop_preview(painter, host, leaf_rects)

    def _paint_drop_preview(self, painter: QPainter, host, leaf_rects) -> None:
        state = host.state
        if state.drag_target_root or not leaf_rects:
            target_rect = host.rect()
        else:
            path = state.drag_target_path
            if path is None:
                return
            node_rect = host._node_rect_at_path(path)
            if node_rect is None:
                return
            target_rect = layout_geometry.side_subrect(
                node_rect, state.drag_target_side
            )
            if target_rect is None:
                return

        accent = self._accent_color(host)
        fill = QColor(accent)
        fill.setAlpha(70)
        painter.setBrush(QBrush(fill))
        painter.setPen(QPen(accent, 2, Qt.PenStyle.SolidLine))
        painter.drawRoundedRect(target_rect.adjusted(2, 2, -2, -2), 6, 6)

        painter.save()
        text_font = QFont(painter.font())
        text_font.setPointSize(max(self.DROP_LABEL_FONT_PT + 2, 12))
        text_font.setBold(True)
        painter.setFont(text_font)
        painter.setPen(QPen(QColor(255, 255, 255)))
        painter.drawText(
            target_rect, int(Qt.AlignmentFlag.AlignCenter), self._drop_hint_text(host)
        )
        painter.restore()

    def _paint_drag_source(self, painter: QPainter, host, leaf_rects) -> None:
        source_id = host.state.drag_source_slot_id
        rect = next((r for l, r in leaf_rects if l.slot_id == source_id), None)
        if rect is None:
            return
        accent = self._accent_color(host)
        painter.save()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(0, 0, 0, 110)))
        painter.drawRoundedRect(rect.adjusted(2, 2, -2, -2), 6, 6)
        painter.setPen(QPen(accent, 2, Qt.PenStyle.DashLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect.adjusted(2, 2, -2, -2), 6, 6)
        painter.restore()

    def _accent_color(self, host) -> QColor:
        c = host.palette().color(QPalette.ColorRole.Highlight)
        if c.isValid() and c.alpha() > 0:
            return c
        return QColor(64, 156, 255)

    def _drop_hint_text(self, host) -> str:
        if host.state.drag_internal:
            if host.state.drag_target_side == "center":
                return host._translate("drop_swap", "Swap")
            return host._translate("drop_move_here", "Move here")
        return host._translate("drop_image_here", "Drop image here")
