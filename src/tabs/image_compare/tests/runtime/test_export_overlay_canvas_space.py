"""Tiled export: canvas-px overlays must be computed against the canvas.

During a tiled export (``engine.gpu.export_tiling``) the offscreen widget is
resized to ONE tile's footprint and ``runtime_state._export_canvas_viewport =
(canvas_w, canvas_h, tile_left, tile_top)`` tells every canvas-px consumer that
its render target is only a slice of the logical canvas. Three sites ignored
that contract, each measured on the production paths before the fix (canvas
8192x4096, tile 4096x4096, no GPU needed):

1. **Root cause** — ``display_tier_service.refresh_live_content_rect`` fitted
   aspect-fit geometry against ``canvas.width()`` (the tile) instead of
   ``canvas_dims(canvas)`` (the canvas): ``_content_rect_px`` came out
   ``(0, 1024, 4096, 2048)`` and ``_content_sr`` = 0.5 instead of
   ``(0, 0, 8192, 4096)`` / 1.0, and with a padded ``geometry_letterbox`` plan
   the base image letterbox became ``(0, 0.25, 1, 0.5)`` — the whole canvas
   squeezed into the middle of every tile.
2. **Divider** — ``resolve_divider_spec`` subtracted ``ctx.canvas_offset_*``
   from ``position_px`` but not from the clip rect, so on a canvas 4096x2048 /
   tile 2048x2048 the right tile drew the line at tile x = -1024 (nowhere) and
   the bar spanned canvas-space y 512..1536 instead of 0..2047. With the clip
   in canvas space the divider shader then discarded any line whose tile-local
   x fell left of a canvas-space clip origin signed into the same uniform.
3. **Magnifier** — ``MagnifierPass.prepare`` projected the lens center with
   the plain ``widget_px_to_screen_px`` defaults (widget size, zero offset), so
   a canvas-px lens landed at the same tile-local point in EVERY tile while the
   root cause above had already halved its radius.

Identity guard: off the tiled path (``_export_canvas_viewport is None``, i.e.
the interactive canvas, a single-frame export, or video preview) every site
must produce exactly the values it produced before — all three sections pin
that, so fixing export cannot drift the live canvas.

Dogma: ``docs/dev/rendering/coordinate-systems.md`` — overlays compute in the
logical canvas space and only the projection subtracts the render-target
origin.
"""

from __future__ import annotations

import os
import struct
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor

from engine.cache import display_tier_service as service
from engine.overlay.semantic import DIVIDER_UNIFORM_FMT
from tabs.image_compare.canvas.features.divider.passes import DividerPass
from tabs.image_compare.canvas.features.magnifier.render.magnifier_pass import (
    _project_canvas_px,
)
from tabs.image_compare.canvas.features.magnifier.render.plan_overlay import (
    apply_magnifier_plan_overlay,
)
from ui.canvas_infra.rhi.render_common import widget_px_to_screen_px
from ui.canvas_infra.viewport.state import ZoomViewportState
from ui.canvas_presentation.plan import CanvasRenderPlan, OverlayLayout, OverlaySlot

CANVAS = (8192, 4096)
TILE = (4096, 4096)


# ---------------------------------------------------------------------------
# Harness: a tile-sized canvas whose runtime_state carries the export viewport
# ---------------------------------------------------------------------------


def _plan_hooks():
    """``LegacyPlanHooks`` with the tab collaborators stubbed out.

    Only the geometry half of ``apply_plan_runtime_overlays`` is under test;
    the feature-overlay hook (registry) and the display-tier bundle are not
    reached by the letterbox/content-rect math.
    """
    return service.LegacyPlanHooks(
        debug=lambda *args, **kwargs: None,
        tier=None,
        apply_feature_plan_runtime_overlays=lambda *args, **kwargs: None,
        apply_feature_live_runtime_overlays=lambda *args, **kwargs: None,
        get_feature_command=lambda *args, **kwargs: None,
        build_render_scene=lambda *args, **kwargs: None,
        make_geometry_actions=lambda *args, **kwargs: [],
        commit_geometry_attrs=lambda *args, **kwargs: None,
    )


class _TileCanvas:
    """Canvas widget stand-in: ``width()/height()`` is the render target.

    ``viewport`` is what the exporter sets per tile
    (``TiledFramebufferExporter._render_tile``); ``None`` is the live/single
    frame case.
    """

    def __init__(self, viewport, *, tile=TILE, zoom=1.0, pan=(0.0, 0.0)):
        self._w, self._h = tile
        self._clip_overlays_to_content_rect = False
        self.runtime_state = SimpleNamespace(
            _store=None,
            _export_canvas_viewport=viewport,
            _content_rect_px=None,
            _letterbox_params=[(0.0, 0.0, 1.0, 1.0), (0.0, 0.0, 1.0, 1.0)],
            _canvas_frame_letterbox=None,
            _letterbox_fill_rgba=None,
            _inner_content_rect_px=None,
            _inner_split_position=None,
            _content_sr=1.0,
            _clip_overlays_to_content_rect=False,
            _capture_circles=[],
            _guide_sets=[],
            _zoom_viewport_state=ZoomViewportState(
                zoom_level=zoom, pan_offset_x=pan[0], pan_offset_y=pan[1]
            ),
        )
        self.overlay_coords = None
        self.gpu_params = None

    def width(self):
        return self._w

    def height(self):
        return self._h

    def clear_feature_overlay_gpu(self):
        raise AssertionError("magnifier overlay must be applied, not cleared")

    def set_overlay_coords(self, capture_center, capture_radius, centers, radius):
        self.overlay_coords = (capture_center, capture_radius, tuple(centers), radius)

    def set_feature_overlay_gpu_params(self, *args):
        self.gpu_params = args


def _export_plan(*, clip, split=0.5, canvas=CANVAS):
    """Export plan: owns the padded framebuffer via ``geometry_letterbox``."""
    return SimpleNamespace(
        canvas_w=canvas[0],
        canvas_h=canvas[1],
        image1=SimpleNamespace(width=canvas[0], height=canvas[1]),
        image2=None,
        image_is_padded_composite=False,
        geometry_letterbox=True,
        fill_rgba=(0, 0, 0, 255),
        render_scene=SimpleNamespace(
            overlay_clip_rect=clip,
            split_position_visual=split,
        ),
    )


def _overlay_ctx(widget, *, canvas=CANVAS, split=0.5, horizontal=False):
    """Frame context as ``render_context.build_render_runtime_context`` shapes it."""
    viewport = widget.runtime_state._export_canvas_viewport
    offset_x, offset_y = (float(viewport[2]), float(viewport[3])) if viewport else (0.0, 0.0)
    zoom_state = widget.runtime_state._zoom_viewport_state
    return SimpleNamespace(
        widget=widget,
        width=widget.width(),
        height=widget.height(),
        canvas_width=canvas[0],
        canvas_height=canvas[1],
        canvas_offset_x=offset_x,
        canvas_offset_y=offset_y,
        zoom_level=zoom_state.zoom_level,
        pan_offset_x=zoom_state.pan_offset_x,
        pan_offset_y=zoom_state.pan_offset_y,
        scene_frame=SimpleNamespace(
            split_position_visual=split,
            split_override=None,
            is_horizontal=horizontal,
            feature_payloads={
                "show_divider": True,
                "divider_thickness": 4,
                "divider_color": QColor(255, 255, 255, 255),
            },
            content_rect_px=None,
        ),
        images_uploaded=[True, True],
    )


def _divider_uniforms(widget, ctx):
    """Run the real ``DividerPass.prepare`` and unpack its 128B block.

    ``DividerPass`` keeps the retained GPU shell (``initialize`` owns the
    pipeline/buffers), so the shell is stubbed: only staging is observed.
    Field order matches ``engine.overlay.semantic.DIVIDER_UNIFORM_FMT``
    (``<24f4fi3f``): mvp(16) resolution(2) position half-thickness color(4)
    clip rect(4) orientation flag pad(3).
    """
    pass_ = DividerPass()
    pass_._shell = SimpleNamespace(
        clip_matrix=lambda: (1.0,) * 16,
        stage_packed=lambda updates, blocks: updates.append(blocks),
    )
    updates: list = []
    pass_.prepare(widget, ctx, updates)
    assert updates and updates[0], "divider pass staged no uniform block"
    block = struct.unpack(DIVIDER_UNIFORM_FMT, updates[0][0])
    return SimpleNamespace(
        resolution=(block[16], block[17]),
        position_px=block[18],
        half_thickness_px=block[19],
        clip=(block[24], block[25], block[26], block[27]),
        is_horizontal=block[28],
    )


def _divider_drawn_at(uniforms, frag_x, frag_y):
    """The divider fragment shader's two discards, inlined.

    Divider fragment shader: discard outside the clip rect, then discard
    anything farther than ``max(0.5, half_thickness_px)`` from
    ``position_px`` on the minor axis. A block that fails the first gate
    paints nothing, which is how a correct line used to vanish on a tile
    seam.
    """
    clip_x, clip_y, clip_w, clip_h = uniforms.clip
    if (
        frag_x < clip_x
        or frag_y < clip_y
        or frag_x > clip_x + clip_w
        or frag_y > clip_y + clip_h
    ):
        return False
    coord = frag_y if uniforms.is_horizontal else frag_x
    return abs(coord - uniforms.position_px) <= max(0.5, uniforms.half_thickness_px)


def _magnifier_layout(center, radius):
    return OverlayLayout(
        slots=(
            OverlaySlot(
                center=QPointF(center[0], center[1]),
                radius=radius,
                uv_rect=(0.0, 0.0, 1.0, 1.0),
                uv_rect2=(0.0, 0.0, 1.0, 1.0),
                source=0,
                is_combined=False,
                internal_split=0.5,
                horizontal=False,
                divider_visible=False,
                divider_color=(1.0, 1.0, 1.0, 1.0),
                divider_thickness_uv=0.0,
                border_color=QColor(255, 255, 255),
                border_width=2.0,
            ),
        ),
        capture_center=QPointF(center[0], center[1]),
        capture_radius=radius,
        overlay_centers=((center[0], center[1]),),
        overlay_radius=radius,
        border_color=QColor(255, 255, 255),
    )


def _magnifier_plan(center, radius, *, canvas=CANVAS):
    return CanvasRenderPlan(
        image1=object(),
        image2=object(),
        source_image1=object(),
        source_image2=object(),
        source_key=("export-overlay-canvas-space",),
        canvas_w=canvas[0],
        canvas_h=canvas[1],
        render_scene=SimpleNamespace(
            overlay_clip_rect=(0, 0, canvas[0], canvas[1]),
            split_position_visual=0.5,
        ),
        overlay_layout=_magnifier_layout(center, radius),
        capture_visible=True,
        capture_color=QColor(255, 255, 255),
        guides_enabled=False,
        guides_color=QColor(255, 255, 255),
        guides_thickness=1,
        # Padded composite: the layout is already in canvas px, no shader
        # letterbox to re-nest — only the content rect / scale is under test.
        image_is_padded_composite=True,
    )


@pytest.fixture(params=[(0, 0), (4096, 0)], ids=["tile-left", "tile-right"])
def tile_origin(request):
    return request.param


# ---------------------------------------------------------------------------
# 1. Root cause: content rect / content scale / shader letterbox are canvas-px
# ---------------------------------------------------------------------------


def test_tiled_content_rect_is_the_full_canvas(tile_origin):
    """Pre-fix: ``(0, 1024, 4096, 2048)`` and ``_content_sr`` = 0.5 per tile."""
    canvas = _TileCanvas((CANVAS[0], CANVAS[1], *tile_origin))

    service.apply_plan_runtime_overlays(
        canvas, _export_plan(clip=(0, 0, CANVAS[0], CANVAS[1])), hooks=_plan_hooks()
    )

    state = canvas.runtime_state
    assert state._content_rect_px == (0, 0, CANVAS[0], CANVAS[1])
    assert state._inner_content_rect_px == (0, 0, CANVAS[0], CANVAS[1])
    # canvas-px -> canvas-px: the isotropic scale (loupe radius, divider
    # thickness, safe gap) must not shrink by the tile/canvas ratio.
    assert state._content_sr == 1.0


def test_tiled_padded_letterbox_frames_the_canvas_not_the_tile(tile_origin):
    """Pre-fix both tiles got ``(0, 0.25, 1, 0.5)`` — canvas squeezed into tile.

    Post-fix the UV params are tile-normalized but canvas-authored: tile
    ``(0, 0)`` sees the canvas frame at ``(0, 0, 2, 1)`` (a 8192-wide frame on
    a 4096-wide tile), tile ``(4096, 0)`` at ``(-1, 0, 2, 1)``.
    """
    canvas = _TileCanvas((CANVAS[0], CANVAS[1], *tile_origin))
    left = tile_origin[0]

    service.apply_plan_runtime_overlays(
        canvas, _export_plan(clip=(0, 0, CANVAS[0], CANVAS[1])), hooks=_plan_hooks()
    )

    state = canvas.runtime_state
    expected = (
        -left / TILE[0],
        0.0,
        CANVAS[0] / TILE[0],
        CANVAS[1] / TILE[1],
    )
    _assert_tuple_close(state._letterbox_params[0], expected)
    _assert_tuple_close(state._letterbox_params[1], expected)
    _assert_tuple_close(state._canvas_frame_letterbox, expected)
    # The frame covers the tile top to bottom: no band of pad-only pixels.
    assert state._canvas_frame_letterbox[1] == pytest.approx(0.0)
    assert state._canvas_frame_letterbox[3] == pytest.approx(1.0)


def test_untiled_content_rect_and_letterbox_are_unchanged():
    """Identity: no export viewport ⇒ the pre-fix numbers, byte for byte.

    Widget 2000x2000 for a 1000x500 canvas (video preview / single-frame
    export): fit height-limited, frame ``(0, 0.25, 1, 0.5)``, clip nested 1:1.
    """
    canvas = _TileCanvas(None, tile=(2000, 2000))
    plan = _export_plan(clip=(0, 0, 1000, 500), canvas=(1000, 500))

    service.apply_plan_runtime_overlays(canvas, plan, hooks=_plan_hooks())

    state = canvas.runtime_state
    assert state._content_rect_px == (0, 500, 2000, 1000)
    # Widget is 2x the canvas, so the canvas-px -> widget-px scale is 2.
    assert state._content_sr == 2.0
    _assert_tuple_close(state._letterbox_params[0], (0.0, 0.25, 1.0, 0.5))
    _assert_tuple_close(state._canvas_frame_letterbox, (0.0, 0.25, 1.0, 0.5))
    assert state._letterbox_fill_rgba == (0.0, 0.0, 0.0, 255.0)


# ---------------------------------------------------------------------------
# 2. Divider: position and clip share the render-target (tile) space
# ---------------------------------------------------------------------------


def test_divider_clip_and_position_are_both_tile_local(tile_origin):
    """Pre-fix: right tile ``position_px`` = -1024, clip stuck at ``(0, 512, 2048, 1024)``.

    Canvas 4096x2048 on a 2048x2048 tile, split 0.5 → the line sits on the
    tile seam at canvas x = 2048: tile-local 2048 (left tile's last column)
    and 0 (right tile's first column).
    """
    canvas = _TileCanvas((4096, 2048, *tile_origin), tile=(2048, 2048))

    service.apply_plan_runtime_overlays(
        canvas, _export_plan(clip=(0, 0, 4096, 2048), canvas=(4096, 2048)),
        hooks=_plan_hooks(),
    )
    uniforms = _divider_uniforms(
        canvas, _overlay_ctx(canvas, canvas=(4096, 2048))
    )

    assert uniforms.resolution == (2048.0, 2048.0)
    assert uniforms.position_px == pytest.approx(2048.0 - tile_origin[0])
    # Same space as the position: the whole canvas shifted by the tile origin.
    _assert_tuple_close(
        uniforms.clip,
        (-float(tile_origin[0]), -float(tile_origin[1]), 4096.0, 2048.0),
    )


def test_divider_at_tile_seam_keeps_drawing_in_both_tiles():
    """A seam-split must be painted by both tiles, not dropped by the clip.

    The shader discards fragments outside the clip rect; with a tile-local
    clip both tiles keep the line (left tile at x = 2047.5, right at 0.25).
    """
    for origin, frag_x in (((0, 0), 2047.5), ((2048, 0), 0.25)):
        canvas = _TileCanvas((4096, 2048, *origin), tile=(2048, 2048))
        service.apply_plan_runtime_overlays(
            canvas, _export_plan(clip=(0, 0, 4096, 2048), canvas=(4096, 2048)),
            hooks=_plan_hooks(),
        )
        uniforms = _divider_uniforms(
            canvas, _overlay_ctx(canvas, canvas=(4096, 2048))
        )
        # The bar's cross-axis extent covers the whole tile height.
        assert uniforms.is_horizontal == 0
        assert uniforms.clip[1] == pytest.approx(0.0)
        assert uniforms.clip[3] == pytest.approx(2048.0)
        assert _divider_drawn_at(uniforms, frag_x, 1024.0) is True


def test_divider_right_of_a_canvas_space_clip_is_not_discarded():
    """Pre-fix second defect: tile-local x < canvas-space ``clip.x`` ⇒ dropped.

    Content clip starts at canvas x = 100; the divider lands at canvas x =
    2100, i.e. tile-local 52 in the right tile. The old block carried a clip
    origin of 100 in that tile, so the shader discarded a line that is inside
    the content. Post-fix the clip travels with the position (``-1948``) and
    the line is drawn.
    """
    canvas = _TileCanvas((4096, 2048, 2048, 0), tile=(2048, 2048))
    split = 2000.0 / 3840.0  # canvas x = 100 + 3840 * split = 2100

    service.apply_plan_runtime_overlays(
        canvas, _export_plan(clip=(100, 0, 3840, 2048), canvas=(4096, 2048), split=split),
        hooks=_plan_hooks(),
    )
    uniforms = _divider_uniforms(
        canvas, _overlay_ctx(canvas, canvas=(4096, 2048), split=split)
    )

    clip_x, clip_y, clip_w, clip_h = uniforms.clip
    # Content box in the right tile starts at 100 - 2048 = -1948.
    assert clip_x == pytest.approx(-1948.0)
    assert clip_x + clip_w == pytest.approx(1892.0)
    assert uniforms.position_px == pytest.approx(52.0)
    assert clip_x <= uniforms.position_px <= clip_x + clip_w
    assert _divider_drawn_at(uniforms, 52.0, 1024.0) is True


def test_divider_is_unchanged_without_an_export_viewport():
    """Identity: interactive canvas ⇒ exactly the pre-fix block.

    ``position_px`` is still ``clip.x + clip.w * split`` and the clip is the
    content rect verbatim, because both offsets are 0.
    """
    canvas = _TileCanvas(None, tile=(4096, 2048), zoom=1.0)

    service.apply_plan_runtime_overlays(
        canvas, _export_plan(clip=(100, 0, 3840, 2048), canvas=(4096, 2048), split=0.25),
        hooks=_plan_hooks(),
    )
    uniforms = _divider_uniforms(
        canvas, _overlay_ctx(canvas, canvas=(4096, 2048), split=0.25)
    )

    assert uniforms.resolution == (4096.0, 2048.0)
    assert uniforms.position_px == pytest.approx(100.0 + 3840.0 * 0.25)
    _assert_tuple_close(uniforms.clip, (100.0, 0.0, 3840.0, 2048.0))


# ---------------------------------------------------------------------------
# 3. Magnifier: canvas-px lens projected through the canvas + tile origin
# ---------------------------------------------------------------------------


def test_magnifier_plan_overlay_keeps_canvas_scale(tile_origin):
    """Pre-fix: slot center halved to (1536, 1024) and radius 150 in every tile."""
    canvas = _TileCanvas((CANVAS[0], CANVAS[1], *tile_origin))
    plan = _magnifier_plan((3072.0, 2048.0), 300.0)

    service.apply_plan_runtime_overlays(canvas, plan, hooks=_plan_hooks())
    apply_magnifier_plan_overlay(canvas, plan)

    centers = canvas.overlay_coords[2]
    assert (centers[0].x(), centers[0].y()) == (3072.0, 2048.0)
    assert canvas.overlay_coords[3] == pytest.approx(300.0)


def test_magnifier_lens_lands_in_the_tile_that_owns_it(tile_origin):
    """One lens, not one per tile at the same tile-local point.

    Canvas x = 3072 belongs to the left tile; its projection is
    ``3072 - tile_left`` — 3072 in the left tile, -1024 (off-target, so
    nothing is drawn) in the right one.
    """
    canvas = _TileCanvas((CANVAS[0], CANVAS[1], *tile_origin))
    plan = _magnifier_plan((3072.0, 2048.0), 300.0)
    service.apply_plan_runtime_overlays(canvas, plan, hooks=_plan_hooks())
    apply_magnifier_plan_overlay(canvas, plan)

    center = canvas.overlay_coords[2][0]
    projected_x, projected_y = _project_canvas_px(
        _overlay_ctx(canvas), canvas, center.x(), center.y()
    )

    assert projected_x == pytest.approx(3072.0 - tile_origin[0])
    assert projected_y == pytest.approx(2048.0)
    assert projected_x < TILE[0]  # only the owning tile gets a drawable center


def test_magnifier_projection_is_unchanged_without_an_export_viewport():
    """Identity: interactive canvas + zoom/pan ⇒ the plain projection, exactly."""
    canvas = _TileCanvas(None, tile=(1280, 720), zoom=2.5, pan=(0.25, -0.1))
    ctx = _overlay_ctx(canvas, canvas=(1280, 720))

    for point in ((400.0, 300.0), (10.0, 700.0), (1280.0, 0.0)):
        assert _project_canvas_px(ctx, canvas, *point) == widget_px_to_screen_px(
            canvas, *point
        )


def _assert_tuple_close(actual, expected, *, tol: float = 1e-9):
    assert len(actual) == len(expected), (actual, expected)
    for got, want in zip(actual, expected):
        assert got == pytest.approx(want, abs=tol), (actual, expected)
