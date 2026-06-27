"""Always-visible split divider overlay for Multi Compare."""

from __future__ import annotations

from PySide6.QtCore import QRect, QRectF
from PySide6.QtGui import QColor, QPainter, QPalette

from tabs.multi_compare.services.composition_builder import DEFAULT_SPLIT_GAP_PX
from tabs.multi_compare.ui import layout_geometry


class DividersOverlaySource:
    """Paints every split gap as an explicit framebuffer overlay."""

    MIN_THICKNESS_FB = 2.0

    def should_paint(self, composition, state) -> bool:
        if composition is None or getattr(state, "root", None) is None:
            return False
        settings = getattr(state, "divider_settings", None)
        if settings is not None and not settings.visible:
            return False
        return True

    def paint(
        self,
        painter: QPainter,
        *,
        host,
        composition,
        state,
        scale: float,
        offset: tuple[float, float],
    ) -> None:
        rects = self.projected_divider_rects(
            composition=composition,
            state=state,
            scale=scale,
            offset=offset,
        )
        if not rects:
            return
        color = self._divider_color(host, state)
        ox, oy = offset
        canvas_clip = QRectF(
            ox, oy, composition.canvas_w * scale, composition.canvas_h * scale
        )
        painter.save()
        painter.setPen(color)
        painter.setBrush(color)
        for rect in rects:
            painter.drawRect(rect.intersected(canvas_clip))
        painter.restore()

    def projected_divider_rects(
        self,
        *,
        composition,
        state,
        scale: float,
        offset: tuple[float, float],
    ) -> tuple[QRectF, ...]:
        if composition is None or getattr(state, "root", None) is None:
            return ()
        if getattr(state, "is_focused", False):
            return ()

        canvas_rect = QRect(0, 0, int(composition.canvas_w), int(composition.canvas_h))
        gaps = layout_geometry.drop_gaps(
            state.root,
            canvas_rect,
            gap=int(DEFAULT_SPLIT_GAP_PX),
        )
        settings = getattr(state, "divider_settings", None)
        thickness_override = float(settings.thickness) if settings is not None else None
        return tuple(
            self._project_gap(
                split.direction, gap_rect, scale, offset, thickness_override
            )
            for split, _path, _index, gap_rect in gaps
        )

    def _project_gap(
        self,
        direction: str,
        rect: QRect,
        scale: float,
        offset: tuple[float, float],
        thickness_canvas: float | None = None,
    ) -> QRectF:
        ox, oy = offset
        x = ox + rect.x() * scale
        y = oy + rect.y() * scale
        w = rect.width() * scale
        h = rect.height() * scale
        if direction == "h":
            thickness = max(self.MIN_THICKNESS_FB, w)
            if thickness_canvas is not None:
                thickness = max(self.MIN_THICKNESS_FB, thickness_canvas * scale)
            center = x + w * 0.5
            return QRectF(center - thickness * 0.5, y, thickness, max(1.0, h))
        thickness = max(self.MIN_THICKNESS_FB, h)
        if thickness_canvas is not None:
            thickness = max(self.MIN_THICKNESS_FB, thickness_canvas * scale)
        center = y + h * 0.5
        return QRectF(x, center - thickness * 0.5, max(1.0, w), thickness)

    def _divider_color(self, host, state=None) -> QColor:
        settings = (
            getattr(state, "divider_settings", None) if state is not None else None
        )
        if settings is not None:
            r, g, b, a = settings.color_rgba
            return QColor(int(r), int(g), int(b), int(a))
        palette = host.palette()
        color = palette.color(QPalette.ColorRole.Mid)
        if not color.isValid() or color.alpha() <= 0:
            color = palette.color(QPalette.ColorRole.WindowText)
        if not color.isValid() or color.alpha() <= 0:
            color = QColor(128, 128, 128)
        color = QColor(color)
        color.setAlpha(230)
        return color
