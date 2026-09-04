"""Live drag/drop overlay painter for Multi Compare."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPalette, QPen

from tabs.multi_compare.debug import mc_dnd_debug, mc_dnd_debug_enabled
from tabs.multi_compare.ui import layout_geometry


def _rect_sig(rect) -> str:
    try:
        return f"{rect.x()},{rect.y()},{rect.width()}x{rect.height()}"
    except Exception:
        return "?"


class DragDropOverlaySource:
    """Paints live-only drag/drop affordances."""

    DROP_LABEL_FONT_PT = 10

    def __init__(self) -> None:
        # Last logged paint/skip signature — edge-triggered ``[mc-dnd]``
        # logging so per-frame ``paint()`` doesn't flood the log.
        self._dbg_sig = None

    def _dbg(self, sig, msg: str, *args) -> None:
        if not mc_dnd_debug_enabled():
            return
        if sig == self._dbg_sig:
            return
        self._dbg_sig = sig
        mc_dnd_debug(msg, *args)

    def reset_debug_state(self) -> None:
        """Forget the last logged signature (called on the active→idle edge
        so the next drag logs its PAINT again even for the same zone)."""
        self._dbg_sig = None

    def should_paint(self, _composition, state) -> bool:
        return bool(state.drag_active)

    def paint(self, painter: QPainter, *, host) -> None:
        leaf_rects = host._leaf_rects()
        if host.state.drag_internal and host.state.drag_source_slot_id is not None:
            self._paint_drag_source(painter, host, leaf_rects)
        self._paint_drop_preview(painter, host, leaf_rects)

    def _paint_drop_preview(self, painter: QPainter, host, leaf_rects) -> None:
        # NOTE: this rasterizes into an offscreen QImage owned by
        # DragDropOverlayPass._raster — not onto the screen. Texture upload
        # (prepare) and the fullscreen quad (record) happen later; the pass
        # logs those stages separately. So the success log below says RASTER
        # (QPainter calls issued), never PAINT.
        state = host.state
        zone_sig = None
        zone_msg = ""
        zone_args: tuple = ()
        if state.drag_target_root or not leaf_rects:
            target_rect = host.rect()
            zone_sig = ("raster", "root")
            zone_msg = "overlay RASTER fullscreen zone rect=%s (empty canvas/root)"
            zone_args = (_rect_sig(target_rect),)
        else:
            path = state.drag_target_path
            if path is None:
                self._dbg(
                    ("skip", "no-path"),
                    "overlay SKIP: drag active but target_path=None side=%s",
                    state.drag_target_side,
                )
                return
            node_rect = host._node_rect_at_path(path)
            if node_rect is None:
                self._dbg(
                    ("skip", "no-node-rect", path),
                    "overlay SKIP: no node rect for path=%s side=%s",
                    path, state.drag_target_side,
                )
                return
            target_rect = layout_geometry.side_subrect(
                node_rect, state.drag_target_side
            )
            if target_rect is None:
                self._dbg(
                    ("skip", "no-subrect", path, state.drag_target_side),
                    "overlay SKIP: no subrect for path=%s side=%s",
                    path, state.drag_target_side,
                )
                return
            swap_id = getattr(state, "drag_target_swap_slot_id", None)
            zone_sig = (
                "raster",
                path,
                state.drag_target_side,
                swap_id,
                state.drag_internal,
                state.drag_source_slot_id,
            )
            zone_msg = (
                "overlay RASTER path=%s side=%s swap=%s internal=%s source=%s rect=%s"
            )
            zone_args = (
                path,
                state.drag_target_side,
                swap_id,
                state.drag_internal,
                state.drag_source_slot_id,
                _rect_sig(target_rect),
            )

        accent = self._accent_color(host)
        fill = QColor(accent)
        fill.setAlpha(70)
        painter.setBrush(QBrush(fill))
        painter.setPen(QPen(accent, 2, Qt.PenStyle.SolidLine))
        painter.drawRoundedRect(target_rect.adjusted(2, 2, -2, -2), 6, 6)

        painter.save()
        # Scale-resolve the drop hint font (painter.font() is the raw
        # design-sized app font; a fixed point size would ignore UiScale).
        text_font = QFont(painter.font())
        text_font.setPointSize(max(self.DROP_LABEL_FONT_PT + 2, 12))
        text_font.setBold(True)
        painter.setFont(text_font)
        painter.setPen(QPen(QColor(255, 255, 255)))
        painter.drawText(
            target_rect, int(Qt.AlignmentFlag.AlignCenter), self._drop_hint_text(host)
        )
        painter.restore()
        # Logged only after the QPainter calls above were issued.
        if zone_sig is not None:
            self._dbg(zone_sig, zone_msg, *zone_args)

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