"""Always-visible split divider overlay for Multi Compare."""

from __future__ import annotations

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QPainter

from domain.qt_adapters import ensure_visible_qcolor
from domain.types import Color
from tabs.multi_compare.models import DEFAULT_DIVIDER_COLOR_RGBA
from ui.widgets.canvas.render_metrics import resolve_relative_px


class DividersOverlaySource:
    """Geometry + style for Multi Compare split dividers.

    Reads gap geometry and styling from the resolved ``ResolvedComposition``
    (``composition.gaps`` / ``composition.divider_settings``) baked by
    ``build_composition_plan`` — live canvas and offscreen export share the
    same snapshot. ``GridDividersPass`` uploads projected rects as GPU quads;
    ``paint()`` remains for CPU/debug paths and contract tests.
    """

    MIN_THICKNESS_FB = 1.0

    def should_paint(self, composition) -> bool:
        if composition is None or not composition.gaps:
            return False
        settings = getattr(composition, "divider_settings", None)
        if settings is not None and not settings.visible:
            return False
        return True

    def paint(
        self,
        painter: QPainter,
        *,
        host,
        composition,
        scale: float,
        offset: tuple[float, float],
        framebuffer_size: tuple[float, float],
    ) -> None:
        rects = self.projected_divider_rects(
            composition=composition,
            scale=scale,
            offset=offset,
            framebuffer_size=framebuffer_size,
        )
        if not rects:
            return
        color = self._divider_color(host, composition)
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
        scale: float,
        offset: tuple[float, float],
        framebuffer_size: tuple[float, float],
    ) -> tuple[QRectF, ...]:
        if composition is None or not composition.gaps:
            return ()
        settings = getattr(composition, "divider_settings", None)
        thickness_override = float(settings.thickness) if settings is not None else None
        fb_w, fb_h = framebuffer_size
        short_edge_fb = min(max(0.0, float(fb_w)), max(0.0, float(fb_h)))
        return tuple(
            self._project_gap(
                gap.direction, gap.rect, scale, offset, thickness_override, short_edge_fb
            )
            for gap in composition.gaps
        )

    def _project_gap(
        self,
        direction: str,
        rect: tuple[int, int, int, int],
        scale: float,
        offset: tuple[float, float],
        thickness_du: float | None = None,
        short_edge_fb: float = 1000.0,
    ) -> QRectF:
        ox, oy = offset
        rx, ry, rw, rh = rect
        x = ox + rx * scale
        y = oy + ry * scale
        w = rw * scale
        h = rh * scale
        # thickness_du is a "du" value (design units against a 1000px
        # reference short edge, same convention as image_compare's
        # guides_stroke_du) — it scales with the current render target
        # (framebuffer_size), not with the composition's fixed native canvas
        # size, so preview and export stay visually WYSIWYG.
        if direction == "h":
            thickness = max(self.MIN_THICKNESS_FB, w)
            if thickness_du is not None:
                thickness = max(
                    self.MIN_THICKNESS_FB,
                    resolve_relative_px(thickness_du, short_edge_px=short_edge_fb),
                )
            center = x + w * 0.5
            return QRectF(center - thickness * 0.5, y, thickness, max(1.0, h))
        thickness = max(self.MIN_THICKNESS_FB, h)
        if thickness_du is not None:
            thickness = max(
                self.MIN_THICKNESS_FB,
                resolve_relative_px(thickness_du, short_edge_px=short_edge_fb),
            )
        center = y + h * 0.5
        return QRectF(x, center - thickness * 0.5, max(1.0, w), thickness)

    def _divider_color(self, host, composition=None) -> QColor:
        del host  # host palette is no longer used — transparent Mid was invisible
        settings = (
            getattr(composition, "divider_settings", None)
            if composition is not None
            else None
        )
        rgba = getattr(settings, "color_rgba", None) if settings is not None else None
        fallback = Color(*DEFAULT_DIVIDER_COLOR_RGBA)
        return ensure_visible_qcolor(rgba, fallback=fallback)
