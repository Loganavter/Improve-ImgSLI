"""Always-visible split divider overlay for Multi Compare."""

from __future__ import annotations

import struct
from typing import Any

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QPainter

from domain.qt_adapters import ensure_visible_qcolor
from domain.types import Color
from engine.overlay import RectItem, Rgba, SemanticOverlayItems
from tabs.multi_compare.models import DEFAULT_DIVIDER_COLOR_RGBA
from ui.canvas_infra.rhi.render_metrics import resolve_relative_px

# Ctx-first resolver block layout (S2 model-side migrate seam onto the S1
# engine overlay shell): mat4 clip_matrix (16f) + divider rect in framebuffer
# px, canvas-clipped (x, y, w, h: 4f) + divider color as float RGBA (4f).
# Pinned by tests/contracts/test_overlay_shell.py
# (test_mc_dividers_exposes_ctx_first_resolver): keep this name until F6
# ratchets that dogma onto the v2 semantic seam (resolve_items below).
# The NDC-quad conversion stays shell-side (S6 mount of GridDividersPass);
# this seam mirrors the IC DividerPass strategy (rect + color in-shader over
# a fullscreen quad) rather than the current hand-rolled NDC vertex upload.
_DIVIDER_BLOCK_FMT = "<24f"
_DIVIDER_BLOCK_SIZE = 96


def _f32(value: float) -> float:
    """Quantize one scalar to float32 (single-rounding parity, F3).

    The v1 bytes seam (``resolve()`` below) carries rects as f32, so the
    retired unpack/repack path ran its NDC math on f32-quantized values.
    Quantizing at the semantic source keeps the shell-packed blocks
    byte-identical to the legacy blocks through the coexistence window
    (double rounding otherwise drifts 1 ulp on non-exact widths such as
    du-resolved thicknesses). Downstream packs to f32 uniforms either way,
    so nothing representable is lost.
    """
    return struct.unpack("<f", struct.pack("<f", float(value)))[0]


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


def resolve_items(ctx: Any) -> SemanticOverlayItems:
    """Ctx-first semantic resolver: ctx in, fb-px divider rects out (F3).

    Owns gap geometry (``DividersOverlaySource.projected_divider_rects``),
    canvas clipping, and color -- one ``RectItem`` per visible divider in
    framebuffer px. Projection stays resolver-side, mirroring the scene
    seam; the shell packs these items via ``pack_grid_dividers`` with the
    frame matrix from ``ctx.clip_matrix`` (no ``canvas_scale`` -- the rects
    arrive projected). The engine forwards ``ctx`` without interpreting it;
    composition/scale/offset/framebuffer stay bound here from the tab's own
    frame sources. Owns no GPU objects: pure ``DividersOverlaySource``
    geometry plus ``ctx`` frame values.
    """
    source = DividersOverlaySource()
    composition = ctx.composition
    if not source.should_paint(composition):
        return ()
    rects = source.projected_divider_rects(
        composition=composition,
        scale=ctx.scale,
        offset=ctx.offset,
        framebuffer_size=ctx.framebuffer_size,
    )
    if not rects:
        return ()
    ox, oy = ctx.offset
    canvas_clip = QRectF(
        ox, oy, composition.canvas_w * ctx.scale, composition.canvas_h * ctx.scale
    )
    color = source._divider_color(None, composition)
    rgba = Rgba(
        float(color.redF()),
        float(color.greenF()),
        float(color.blueF()),
        float(color.alphaF()),
    )
    items: list[RectItem] = []
    for rect in rects:
        clipped = rect.intersected(canvas_clip)
        if clipped.width() <= 0.0 or clipped.height() <= 0.0:
            continue
        items.append(
            RectItem(
                _f32(clipped.x()),
                _f32(clipped.y()),
                _f32(clipped.width()),
                _f32(clipped.height()),
                rgba,
            )
        )
    return tuple(items)


def resolve(ctx: Any) -> tuple[bytes, ...]:
    """Ctx-first uniform-block resolver for MC grid dividers (S2 migrate seam).

    Takes the opaque per-frame pass context first and returns packed uniform
    blocks (engine types: ``tuple[bytes, ...]``) -- one ``_DIVIDER_BLOCK_FMT``
    block per visible divider. Geometry is single-sourced from
    ``resolve_items()`` above (gap semantics the shell packs); this v1 bytes
    seam stays alive through the F-b..F-c coexistence window until F6
    retires it with the ``_DIVIDER_BLOCK_FMT`` layout (both pinned by
    ``test_mc_dividers_exposes_ctx_first_resolver``).

    Not yet consumed: ``GridDividersPass`` (``canvas/features/grid_dividers``)
    now packs ``resolve_items()`` shell-side via ``pack_grid_dividers``;
    this entry remains for the v1 bytes consumers until the F6 flag-day
    deletes it (lift-then-delete) -- do not duplicate this format elsewhere,
    call ``resolve_items``.
    """
    items = resolve_items(ctx)
    if not items:
        return ()
    matrix = tuple(float(value) for value in ctx.clip_matrix)
    return tuple(
        struct.pack(
            _DIVIDER_BLOCK_FMT,
            *matrix,
            item.x,
            item.y,
            item.w,
            item.h,
            item.color.r,
            item.color.g,
            item.color.b,
            item.color.a,
        )
        for item in items
    )
