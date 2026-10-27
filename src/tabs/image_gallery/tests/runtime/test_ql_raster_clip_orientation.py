"""Quick Look raster path: raster row 0 must land on the framebuffer's TOP row.

The preview canvas has two paths for the same widget: the tiled path
(``engine/gpu/tiled_image_view.py``, which passes
``composited_clip_correction(rhi)``) and the raster path, which is its
**fallback** -- ``preview_canvas/rhi_entry.py`` renders a frame through
``TexturedOverlayShell`` whenever no resident tile is available yet, and every
frame before the tile set takes over. The raster path staged a hardcoded
identity matrix instead, so the two paths of one canvas answered the Y question
differently: on a y-down NDC backend (Vulkan, Metal) the raster preview read
mirrored vertically and then "fixed itself" the moment the tiles arrived.

Why the matrix is the only place this can be fixed
--------------------------------------------------
``engine/overlay/shell.py`` ``FULLSCREEN_VERTICES`` puts the vertex carrying
raster row 0 (``v == 0``) at clip ``y = +1``. Whether ``+1`` is the top of the
framebuffer is a backend convention, and the raster is uploaded top-down
(``preview_canvas/raster.py`` takes ``target.pixelSize()`` bytes as-is,
``engine/overlay/textured.py`` uploads them unflipped), so no downstream step
compensates. The sanctioned answer is the single source of truth,
``engine/gpu/rt_y_orientation.composited_clip_correction`` -- the ``COMPOSITED``
case, because this pass writes into the ``QRhiWidget``'s own composited target.
The sibling shells/passes already do that (``engine/overlay/shell.py``
``clip_matrix()``; image_compare's guides/capture/divider; the 2026-10-27
``drag_drop_overlay`` fix). Never by reversing raster rows or UVs.

Red-before (proven at 167b9d820): ``test_raster_top_row_is_not_mirrored`` fails
for ``y_down_ndc=True`` -- the staged matrix is identity, so raster row 0 is
drawn at clip y=+1, i.e. the *bottom* row of a y-down framebuffer.

Runs offscreen (no window, no GPU): the real ``rhi_entry.render`` seam is
driven through stub rhi/command-buffer/shell objects, and the shell records the
matrix the pass itself staged. The assertions are about where raster row 0
lands, not about "some matrix" being staged.
"""

from __future__ import annotations

import os
import struct

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtGui import QMatrix4x4

from engine.overlay.shell import FULLSCREEN_VERTICES

from tabs.image_gallery.ui.quick_look.preview_canvas import rhi_entry

_WIDTH = 64
_HEIGHT = 64


# ---------------------------------------------------------------------------
# Quad / clip-space math (the same quad bytes the shell uploads)
# ---------------------------------------------------------------------------


def _quad_vertices() -> list[tuple[float, float, float, float]]:
    """``(x, y, u, v)`` per vertex of the quad the shell actually uploads."""
    values = struct.unpack("<16f", FULLSCREEN_VERTICES)
    return [tuple(values[i : i + 4]) for i in range(0, 16, 4)]  # type: ignore[misc]


def _clip_y(matrix: tuple[float, ...], x: float, y: float) -> float:
    """GLSL ``(mat4 * vec4(x, y, 0, 1)).y`` for a column-major std140 mat4.

    The uniform block is ``struct.pack("<16f", *matrix)`` fed to ``mat4 mvp``
    (``overlay.vert``), i.e. column-major: the y row of the matrix is flat
    index 1, 5, 9, 13.
    """
    return matrix[1] * x + matrix[5] * y + matrix[9] * 0.0 + matrix[13]


def _raster_top_row_lands_on_screen_top(
    matrix: tuple[float, ...], *, y_down_ndc: bool
) -> bool:
    """True when the raster's first row is drawn at the framebuffer's top.

    Clip y = -1 is the top row on a y-down NDC backend (Vulkan/Metal), +1 on a
    y-up one (OpenGL/D3D). The quad's ``v == 0`` vertices carry raster row 0.
    """
    top_vertices = [vertex for vertex in _quad_vertices() if vertex[3] == 0.0]
    assert top_vertices, "engine/overlay/shell.py quad lost its v=0 vertices"
    x, y, _u, _v = top_vertices[0]
    top_clip_y = -1.0 if y_down_ndc else 1.0
    return abs(_clip_y(matrix, x, y) - top_clip_y) < 1e-6


# ---------------------------------------------------------------------------
# fakes: a backend stub carrying only what rt_y_orientation reads, a staging
# shell that records the pass's own per-frame matrix, and a canvas host shaped
# like ``QuickLookCanvasWidget`` as ``render()`` sees it.
# ---------------------------------------------------------------------------


class _Batch:
    """Distinct sentinel per ``nextResourceUpdateBatch()`` call."""

    __slots__ = ("n",)

    def __init__(self, n: int) -> None:
        self.n = n


class _FakeRhi:
    """Backend stub: ``clipSpaceCorrMatrix`` + the two convention queries."""

    def __init__(self, *, y_down_ndc: bool) -> None:
        self._y_down_ndc = bool(y_down_ndc)
        matrix = QMatrix4x4()
        matrix.setToIdentity()
        if self._y_down_ndc:
            # What QRhi returns on Vulkan/Metal: clip-space y points down, so
            # the composited correction flips it back.
            matrix.scale(1.0, -1.0, 1.0)
        self._correction = matrix
        self.handed: list[_Batch] = []

    def clipSpaceCorrMatrix(self) -> QMatrix4x4:
        return self._correction

    def isYUpInNDC(self) -> bool:
        return not self._y_down_ndc

    def isYUpInFramebuffer(self) -> bool:
        return not self._y_down_ndc

    def nextResourceUpdateBatch(self) -> _Batch:
        batch = _Batch(len(self.handed) + 1)
        self.handed.append(batch)
        return batch


class _FakeCmd:
    """Consumes batches by identity (beginPass / resourceUpdate). None GPU."""

    def __init__(self) -> None:
        self.consumed: list[_Batch] = []

    def resourceUpdate(self, batch) -> None:
        self.consumed.append(batch)

    def beginPass(self, target, clear, depth_clear, batch) -> None:
        self.consumed.append(batch)

    def endPass(self) -> None:
        return None


class _StagingShell:
    """Records what the pass stages instead of touching the GPU."""

    def __init__(self) -> None:
        self.active = True
        self.pipeline = object()
        self.quad_calls = 0
        self.upload_calls = 0
        self.draw_calls = 0
        self.clip: tuple[float, ...] | None = None

    def stage_quad(self, updates) -> None:
        self.quad_calls += 1

    def stage_clip(self, updates, clip_matrix) -> None:
        self.clip = tuple(float(value) for value in clip_matrix)

    def upload_frame(self, updates, target, frame, **kwargs) -> bool:
        self.upload_calls += 1
        return frame is not None

    def draw(self, command_buffer, *, width=0.0, height=0.0) -> None:
        self.draw_calls += 1


def _target(w: int = _WIDTH, h: int = _HEIGHT):
    from types import SimpleNamespace

    return SimpleNamespace(
        pixelSize=lambda: SimpleNamespace(width=lambda: w, height=lambda: h)
    )


class _FakeWidget:
    """Pure-Python stand-in for ``QuickLookCanvasWidget`` as ``render()`` sees it."""

    def __init__(self, rhi, *, shell=None, frame=None) -> None:
        self._rhi = rhi
        self._shell = shell if shell is not None else _StagingShell()
        self._target = _target()
        self._frame = frame
        self._shell_ready = True
        self._frame_ok = True
        self._tiled_source = None
        self._zoom = 1.0
        self._pan_x = 0.0
        self._pan_y = 0.0
        self.pumps = 0

    # -- QRhiWidget surface used by render() --------------------------------
    def rhi(self):
        return self._rhi

    def renderTarget(self):
        return self._target

    def isVisible(self) -> bool:
        return True

    def width(self) -> int:
        return _WIDTH

    def height(self) -> int:
        return _HEIGHT

    # -- rhi_entry module functions, bound as methods -----------------------
    def _skip_frame(self, reason) -> None:
        return rhi_entry._skip_frame(self, reason)

    def _render_tiled(self, *args, **kwargs):
        return rhi_entry._render_tiled(self, *args, **kwargs)

    def _ql_view_hooks(self):
        return rhi_entry._ql_view_hooks(self)

    def _tiled_level_ready(self) -> bool:
        return False

    # -- frame plumbing -----------------------------------------------------
    def _raster_frame(self, target):
        return self._frame

    def _ensure_tile_renderer(self):
        return None

    def _settle_present(self) -> None:
        return None

    def _pump_next_frame(self) -> None:
        self.pumps += 1

    def _pump_throttled(self, stall_frames) -> None:
        self.pumps += 1


_RASTER_FRAME = (_WIDTH, _HEIGHT, bytes(_WIDTH * _HEIGHT * 4))


def _rendered(rhi, *, frame=_RASTER_FRAME) -> _StagingShell:
    """Drive the real ``rhi_entry.render`` raster path; return the shell."""
    shell = _StagingShell()
    widget = _FakeWidget(rhi, shell=shell, frame=frame)
    rhi_entry.render(widget, _FakeCmd())
    return shell


# ---------------------------------------------------------------------------
# orientation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "y_down_ndc, backend",
    [(True, "vulkan-like y-down NDC"), (False, "opengl-like y-up NDC")],
)
def test_raster_top_row_is_not_mirrored(y_down_ndc, backend):
    """Raster row 0 must land on the framebuffer's TOP row on every backend.

    This is the raster half of the QL preview mirroring: the quad maps
    ``v=0`` (raster top) to clip y=+1, so the raster pass has to stage the
    backend's clip-space correction. Identity satisfies the y-up backend and
    mirrors the y-down one.
    """
    shell = _rendered(_FakeRhi(y_down_ndc=y_down_ndc))
    assert shell.clip is not None, "the raster path staged no clip matrix"
    assert _raster_top_row_lands_on_screen_top(shell.clip, y_down_ndc=y_down_ndc), (
        f"raster row 0 does not land on the top screen row on a {backend}: "
        f"the staged clip matrix is {shell.clip} -- the raster pass must use "
        f"engine/gpu/rt_y_orientation.composited_clip_correction, not identity"
    )


def test_raster_path_uses_the_single_source_correction():
    """The staged matrix *is* the SSOT composited correction (no local copy)."""
    from engine.gpu.rt_y_orientation import composited_clip_correction

    rhi = _FakeRhi(y_down_ndc=True)
    shell = _rendered(rhi)
    expected = tuple(float(value) for value in composited_clip_correction(rhi))
    assert shell.clip == expected


def test_no_identity_clip_literal_stays_available():
    """A local identity matrix must not exist as a ready-made answer.

    The defect was one literal plus one call site: leaving ``_IDENTITY_CLIP``
    importable re-arms the same mistake, so it is gone from both the phase
    module and the package re-exports.
    """
    from tabs.image_gallery.ui.quick_look.preview_canvas import (
        __init__ as preview_canvas,
    )

    assert not hasattr(rhi_entry, "_IDENTITY_CLIP")
    assert not hasattr(preview_canvas, "_IDENTITY_CLIP")
