"""Immediate-overlay pilot: stateless divider-spec resolver (Engine Phase 3).

Pure decision + geometry layer for ``DividerPass``. Every public function
takes the frame context first and returns frozen plain data — no QRhi
objects, no uniform buffers, no pipelines, no module-level mutable
state, no ``store`` import, no export-mode branch. ``DividerPass``
(``passes.py``) keeps the retained GPU shell its ``CanvasRenderPass``
contract requires (``initialize``-owned pipeline/buffers, ``prepare`` →
``resource_updates`` staging, ``record`` draw) and delegates all spec
decisions here, so live and snapshot rendering share one source of
truth.

Retained on purpose (see ``test_overlay_stateless.py``): pipeline /
buffer ownership stays in the pass — creating them per frame would
recompile shaders every frame, and
``tests/contracts/test_pass_reads_only_ctx.py`` pins ``record()`` as
"ctx plus its own retained GPU resources".
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtGui import QColor

from tabs.image_compare.canvas.render_config import (
    get_view_transformed_content_rect_widget_px,
)

__all__ = ["DividerSpec", "content_split_visual", "resolve_divider_spec"]


@dataclass(frozen=True, slots=True)
class DividerSpec:
    """Divider line for this frame, fully resolved (plain data).

    ``position_px`` and ``clip_*`` are in render-target px — tile-local during
    tiled export (both shifted by ``ctx.canvas_offset_*``), so the packed
    uniform's clip rect and the fragment px the divider shader tests share one
    space. See ``resolve_divider_spec``.
    """

    show: bool
    position_px: float
    thickness_px: float
    is_horizontal: bool
    red: float
    green: float
    blue: float
    alpha: float
    clip_x: float
    clip_y: float
    clip_w: float
    clip_h: float


def content_split_visual(ctx) -> float:
    """Clamped visual split fraction for this frame (pure)."""
    scene = getattr(ctx, "scene_frame", None)
    raw = getattr(scene, "split_position_visual", 0.5)
    split_override = getattr(scene, "split_override", None)
    if split_override is not None:
        raw = split_override
    return max(0.0, min(1.0, float(raw if raw is not None else 0.5)))


def resolve_divider_spec(ctx, widget) -> DividerSpec:
    """Resolve the divider line for this frame from the context (pure).

    Reads ``ctx.scene_frame.feature_payloads`` (show / thickness /
    color), ``ctx.scene_frame.is_horizontal`` + split, and the
    view-transformed content rect only. Calling twice with an unchanged
    frame yields an equal spec; nothing is cached, stored, or mutated.
    """
    payloads = (
        ctx.scene_frame.feature_payloads
        if isinstance(getattr(ctx.scene_frame, "feature_payloads", None), dict)
        else {}
    )
    show_divider = bool(payloads.get("show_divider", False))
    thickness_px = float(payloads.get("divider_thickness", 0) or 0)
    color = QColor(payloads.get("divider_color", QColor(255, 255, 255, 255)))
    is_horizontal = bool(getattr(ctx.scene_frame, "is_horizontal", False))
    split = content_split_visual(ctx)

    # Position + clip from the letterbox *after* the same zoom/pan as
    # base.frag. See src/tabs/image_compare/docs/investigations/divider-zoom-pan-detach.md.
    clip = get_view_transformed_content_rect_widget_px(widget)
    if clip is None:
        clip = (0.0, 0.0, float(ctx.canvas_width), float(ctx.canvas_height))
    cx, cy, cw, ch = (float(v) for v in clip)
    # One space for both: the pass packs a tile-local bar and the divider
    # shader compares fragment px against its clip-rect uniform, so the clip
    # must be shifted by the tile origin exactly like the position. Leaving the
    # clip in canvas px dropped lines whose tile-local x fell left of a
    # canvas-space clip origin (the shader discards them as "outside the
    # content") and put the bar's cross-axis extent in the wrong space during
    # tiled export (owner report 2026-10-28). Offsets are 0 off the tiled path,
    # where this resolves to the pre-fix expression unchanged.
    offset_x = float(getattr(ctx, "canvas_offset_x", 0.0) or 0.0)
    offset_y = float(getattr(ctx, "canvas_offset_y", 0.0) or 0.0)
    cx -= offset_x
    cy -= offset_y
    if is_horizontal:
        position_px = cy + ch * split
    else:
        position_px = cx + cw * split

    return DividerSpec(
        show=show_divider,
        position_px=position_px,
        thickness_px=thickness_px,
        is_horizontal=is_horizontal,
        red=color.redF(),
        green=color.greenF(),
        blue=color.blueF(),
        alpha=color.alphaF(),
        clip_x=cx,
        clip_y=cy,
        clip_w=cw,
        clip_h=ch,
    )
