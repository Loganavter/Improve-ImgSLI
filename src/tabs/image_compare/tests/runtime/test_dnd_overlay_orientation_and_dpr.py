"""DnD overlay orientation + DPR: the zone must not mirror and must not shrink.

Two owner-reported symptoms (image_compare, 2026-10-27 screenshot):

1. the drop zone's text and preview read **mirrored top-to-bottom**;
2. at a non-1 device pixel ratio the zone got **smaller** instead of keeping
   the same size in logical px.

Orientation
-----------
The pass draws one fullscreen quad; the vertex that carries raster row 0
(``v == 0``) sits at clip ``y = +1`` (see ``engine/overlay/shell.py``
``FULLSCREEN_VERTICES``). Whether ``+1`` is the top of the framebuffer is a
backend convention (y-up NDC on GL/D3D, y-down on Vulkan), and the only
sanctioned correction is ``engine/gpu/rt_y_orientation`` --
``composited_clip_correction`` for a pass that writes into a ``QRhiWidget``'s
own composited target. That is what the sibling shells/passes use
(``engine/overlay/shell.py`` ``clip_matrix()``, and image_compare's
``features/guides``, ``features/capture``, ``features/divider``). The drag pass
staged a hardcoded identity matrix instead, so on a y-down backend the raster
arrives row-reversed. These tests drive the quad through the *real* staged
matrix and assert where raster row 0 lands, per backend convention -- not that
"some matrix" was staged.

DPR
---
image_compare's render context carries *logical* ``viewport.width/height``
(``canvas/render_context.py``). The raster was sized ``logical x DPR`` (device
px) but ``record()`` set the viewport to the same logical numbers, so the quad
covered ``1/DPR`` of the framebuffer per axis (a quarter of the area at DPR=2)
-- the zone shrank by the scale factor. Raster size and viewport have to come
from ONE resolution of the framebuffer size, which is what these tests pin.

Red-before (proven at 513eeed73): ``test_dnd_overlay_raster_top_row_is_not_mirrored``
fails (identity staged -> raster row 0 drawn at clip y=+1 on a y-down backend)
and ``test_dnd_overlay_covers_the_whole_frame_at_any_dpr`` fails
(viewport 800x600 against a 1600x1200 raster -> share 0.25).

Runs offscreen (no window, no GPU): the real raster is painted into a QImage
and the real prepare/record seam is recorded through a stub shell, so the
matrix and the viewport are the pass's own values, not a re-implementation.
"""

from __future__ import annotations

import os
import struct
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QSize
from PySide6.QtGui import QFont, QMatrix4x4

from engine.overlay.shell import FULLSCREEN_VERTICES

from tabs.image_compare.canvas.features.drag_drop_overlay.passes import (
    DragDropOverlayPass,
)

_WIDTH = 800
_HEIGHT = 600


# ---------------------------------------------------------------------------
# Quad / clip-space math (the same bytes the shell stages)
# ---------------------------------------------------------------------------


def _quad_vertices() -> list[tuple[float, float, float, float]]:
    """``(x, y, u, v)`` per vertex of the quad the shell actually uploads."""
    values = struct.unpack("<16f", FULLSCREEN_VERTICES)
    return [tuple(values[i : i + 4]) for i in range(0, 16, 4)]  # type: ignore[misc]


def _clip_y(matrix: tuple[float, ...], x: float, y: float) -> float:
    """GLSL ``(mat4 * vec4(x, y, 0, 1)).y`` for a column-major std140 mat4.

    The uniform block is ``struct.pack("<16f", *matrix)`` fed to ``mat4 mvp``
    (``overlay.vert``), i.e. column-major: ``m[1][1]`` is flat index 5.
    """
    return matrix[1] * x + matrix[5] * y + matrix[9] * 0.0 + matrix[13]


def _raster_top_row_lands_on_screen_top(
    matrix: tuple[float, ...], *, y_down_ndc: bool
) -> bool:
    """True when the raster's first row is drawn at the framebuffer's top.

    Clip y = -1 is the top row on a y-down NDC backend (Vulkan), +1 on a y-up
    one (GL/D3D). The quad's ``v == 0`` vertices carry raster row 0.
    """
    top_vertices = [vertex for vertex in _quad_vertices() if vertex[3] == 0.0]
    assert top_vertices, "engine/overlay/shell.py quad lost its v=0 vertices"
    x, y, _u, _v = top_vertices[0]
    top_clip_y = -1.0 if y_down_ndc else 1.0
    return abs(_clip_y(matrix, x, y) - top_clip_y) < 1e-6


# ---------------------------------------------------------------------------
# Fakes: a backend stub carrying only what rt_y_orientation reads, a staging
# shell that records the pass's own per-frame values, and a canvas host shaped
# like the real image_compare widget (logical width/height + DPR + target).
# ---------------------------------------------------------------------------


class _FakeRhi:
    """Backend stub: ``clipSpaceCorrMatrix`` + the two convention queries."""

    def __init__(self, *, y_down_ndc: bool) -> None:
        self._y_down_ndc = bool(y_down_ndc)
        matrix = QMatrix4x4()
        matrix.setToIdentity()
        if self._y_down_ndc:
            # What QRhi returns on Vulkan: clip-space y points down, so the
            # composited correction flips it back.
            matrix.scale(1.0, -1.0, 1.0)
        self._correction = matrix

    def clipSpaceCorrMatrix(self) -> QMatrix4x4:
        return self._correction

    def isYUpInNDC(self) -> bool:
        return not self._y_down_ndc

    def isYUpInFramebuffer(self) -> bool:
        return not self._y_down_ndc


class _StagingShell:
    """Records what the pass stages/draws instead of touching the GPU."""

    def __init__(self, rhi) -> None:
        self.rhi = rhi
        self.active = True
        self.pipeline = object()
        self.texture_size = QSize(0, 0)
        self.clip_matrix: tuple[float, ...] | None = None
        self.frame: tuple[int, int, bytes] | None = None
        self.draw_size: tuple[float, float] | None = None

    def stage_quad(self, resource_updates) -> None:
        return None

    def stage_clip(self, resource_updates, clip_matrix) -> None:
        self.clip_matrix = tuple(float(v) for v in clip_matrix)

    def upload_frame(self, resource_updates, render_target, frame, **_kwargs) -> bool:
        self.frame = frame
        return frame is not None

    def draw(self, command_buffer, *, width, height) -> None:
        self.draw_size = (float(width), float(height))


class _Updates:
    """Stand-in for QRhiResourceUpdateBatch (the pass never looks inside)."""


def _host(dpr: float = 1.0, *, width: int = _WIDTH, height: int = _HEIGHT):
    font = QFont()
    state = SimpleNamespace(
        _drag_overlay_visible=True,
        _drag_overlay_horizontal=False,
        _drag_overlay_texts=("one", "two"),
        _drag_overlay_cache_key=None,
        _drag_overlay_cached_image=None,
    )
    from PySide6.QtWidgets import QWidget

    pixel_size = QSize(int(round(width * dpr)), int(round(height * dpr)))
    target = SimpleNamespace(pixelSize=lambda: pixel_size)
    return SimpleNamespace(
        runtime_state=state,
        width=lambda: width,
        height=lambda: height,
        devicePixelRatioF=lambda: dpr,
        renderTarget=lambda: target,
        font=lambda: font,
        property=lambda name: None,
        palette=lambda: QWidget().palette(),
    )


def _ctx(host):
    """image_compare's ctx shape: logical width/height, no framebuffer_size."""
    return SimpleNamespace(widget=host, width=_WIDTH, height=_HEIGHT)


def _prepared(rhi=None, host=None):
    """Run the real prepare/record seam; return (pass, shell, ctx, host)."""
    host = host if host is not None else _host()
    ctx = _ctx(host)
    drag_pass = DragDropOverlayPass()
    shell = _StagingShell(rhi if rhi is not None else _FakeRhi(y_down_ndc=False))
    drag_pass._shell = shell  # no GPU in this test: record instead of draw
    drag_pass.prepare(host, ctx, _Updates())
    return drag_pass, shell, ctx, host


# ---------------------------------------------------------------------------
# Orientation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "y_down_ndc, backend",
    [(True, "vulkan-like y-down NDC"), (False, "opengl-like y-up NDC")],
)
def test_dnd_overlay_raster_top_row_is_not_mirrored(qapp, y_down_ndc, backend):
    """Raster row 0 must land on the framebuffer's TOP row on every backend.

    This is the owner's "text/preview mirrored vertically" symptom: the quad
    maps ``v=0`` (raster top) to clip y=+1, so the pass has to stage the
    backend's clip-space correction. Staging identity satisfies the y-up
    backend and mirrors the y-down one.
    """
    _pass, shell, _ctx_, _host_ = _prepared(_FakeRhi(y_down_ndc=y_down_ndc))
    assert shell.clip_matrix is not None, "prepare() staged no clip matrix"
    assert _raster_top_row_lands_on_screen_top(
        shell.clip_matrix, y_down_ndc=y_down_ndc
    ), (
        f"raster row 0 does not land on the top screen row on a {backend}: "
        f"the staged clip matrix is {shell.clip_matrix} -- the pass must use "
        f"engine/gpu/rt_y_orientation.composited_clip_correction, not identity"
    )


def test_dnd_overlay_uses_the_single_source_correction(qapp):
    """The staged matrix *is* the SSOT composited correction (no local flip)."""
    from engine.gpu.rt_y_orientation import composited_clip_correction

    rhi = _FakeRhi(y_down_ndc=True)
    _pass, shell, _ctx_, _host_ = _prepared(rhi)
    expected = tuple(float(v) for v in composited_clip_correction(rhi))
    assert shell.clip_matrix == expected


# ---------------------------------------------------------------------------
# DPR
# ---------------------------------------------------------------------------


def test_dnd_overlay_covers_the_whole_frame_at_any_dpr(qapp):
    """Viewport and raster must agree: DPR is applied exactly once.

    At DPR=2 the raster is 1600x1200 device px; a viewport of the logical
    800x600 draws that texture into a quarter of the framebuffer -- the zone
    shrinks instead of scaling up (owner's second symptom).
    """
    shares: dict[float, float] = {}
    for dpr in (1.0, 2.0):
        host = _host(dpr=dpr)
        drag_pass, shell, ctx, _host_ = _prepared(host=host)
        drag_pass.record(object(), host, ctx)
        assert shell.frame is not None, f"no raster staged at dpr={dpr}"
        frame_w, frame_h = int(shell.frame[0]), int(shell.frame[1])
        assert (frame_w, frame_h) == (
            int(round(_WIDTH * dpr)),
            int(round(_HEIGHT * dpr)),
        ), f"raster is not device-px at dpr={dpr}: {(frame_w, frame_h)}"
        assert shell.draw_size is not None, f"record() drew nothing at dpr={dpr}"
        draw_w, draw_h = shell.draw_size
        shares[dpr] = (draw_w / frame_w) * (draw_h / frame_h)

    assert shares[1.0] == pytest.approx(1.0), "the quad must fill the frame at DPR=1"
    assert shares[2.0] == pytest.approx(1.0), (
        f"at DPR=2 the overlay covers {shares[2.0]:.2f} of the frame (0.25 = a "
        f"quarter): the viewport is in logical px while the raster is in device "
        f"px -- resolve both from one framebuffer size"
    )


def test_dnd_overlay_keeps_logical_geometry_at_any_dpr(qapp):
    """The painted tiles keep their design-px geometry at DPR 1 and 2.

    Guards the other half of the DPR rule: the raster is scaled by DPR and
    painted in logical coordinates, so the covered fraction of the frame is
    DPR-independent (design colors/margins untouched).
    """
    fractions: dict[float, float] = {}
    for dpr in (1.0, 2.0):
        _pass, shell, _ctx_, _host_ = _prepared(host=_host(dpr=dpr))
        assert shell.frame is not None
        width, height, pixels = shell.frame
        fractions[dpr] = _grid_coverage(pixels, width, height)

    assert fractions[1.0] > 0.3, f"tiles cover only {fractions[1.0]:.2f}"
    assert fractions[2.0] == pytest.approx(fractions[1.0], abs=0.05), (
        f"tile coverage drifted with DPR ({fractions[1.0]:.2f} at 1x vs "
        f"{fractions[2.0]:.2f} at 2x) -- design geometry must not depend on DPR"
    )


def _grid_coverage(pixels: bytes, width: int, height: int) -> float:
    """Fraction of a 40x30 logical grid whose centre pixel is non-transparent."""
    stride = width * 4
    hits = 0
    columns, rows = 40, 30
    for row in range(rows):
        y = min(height - 1, int((row + 0.5) * height / rows))
        line = pixels[y * stride : (y + 1) * stride]
        for column in range(columns):
            x = min(width - 1, int((column + 0.5) * width / columns))
            if line[x * 4 + 3]:
                hits += 1
    return hits / float(columns * rows)
