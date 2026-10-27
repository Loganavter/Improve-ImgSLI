"""Image Compare's render context carries the frame's target units.

Two 2026-10-27/28 defects came from the *same* gap in
``tabs/image_compare/canvas/render_context.py`` ``ViewportContext``: it carried
logical ``width/height`` only, so every composite pass that needed the
backend's clip-space correction or the real framebuffer size had to invent a
local answer:

* drag_drop_overlay staged an identity matrix instead of
  ``engine/gpu/rt_y_orientation.composited_clip_correction`` -> the zone read
  mirrored on a y-down NDC backend (#751);
* a viewport was sized from the *logical* width while the raster was in device
  px -> a quarter of the frame at DPR=2.

The class fix is the two fields multi_compare's context already carries
(``tabs/multi_compare/scene/context.py``: ``clip_matrix``,
``framebuffer_size``; filled in ``scene/renderer.py`` from
``target.pixelSize()`` + ``composited_clip_correction(rhi)``), plus one
tab-side resolver so the value is computed once:

    resolve_target_units(widget) -> (clip_matrix | None, framebuffer_size)

``None`` for the matrix is a legal state ("no RHI yet" -- before mount), which
is why the pass still owns the identity fallback: a context may not pretend to
know a backend convention it cannot ask for. ``framebuffer_size`` is always
resolved (target pixel size, else logical x DPR).

The other half is ``filename_overlay.record``: it was the one IC pass that
recomputed the framebuffer size as ``ctx.width * dpr`` instead of reading
``renderTarget().pixelSize()`` like its six siblings. The numbers agree today
and diverge on a fractional DPR or an independently resized target.

Red-before (base ``230431a52``): ``resolve_target_units`` does not exist
(ImportError) and ``ViewportContext`` has neither field (AttributeError); the
``framing``/``filename_overlay`` regression tests in this file are green on the
base already -- they pin the fallbacks this change must not break.

Runs offscreen, no GPU: the backend is a stub that answers only what
``rt_y_orientation`` queries, and the passes record into a fake command buffer.
"""

from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QSize
from PySide6.QtGui import QMatrix4x4

from engine.gpu.rt_y_orientation import (
    IDENTITY_MATRIX,
    composited_clip_correction,
)
from tabs.image_compare.canvas.features.drag_drop_overlay.framing import (
    clip_matrix as framing_clip_matrix,
)
from tabs.image_compare.canvas.features.filename_overlay.passes import (
    FilenameOverlayPass,
)


# ---------------------------------------------------------------------------
# Stubs: a backend that answers only the two convention queries, a host shaped
# like the real image_compare widget (logical size + DPR + rhi + target).
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


def _host(
    *,
    dpr: float = 1.0,
    width: int = 800,
    height: int = 600,
    rhi=None,
    with_target: bool = True,
    target_size: QSize | None = None,
):
    """A canvas host: logical size, DPR, ``rhi()`` and (optionally) a target.

    ``target_size`` overrides the target's pixel size, for the case the two
    resolutions disagree (target resized independently of the widget).
    """
    host = SimpleNamespace(
        runtime_state=SimpleNamespace(),
        width=lambda: width,
        height=lambda: height,
        devicePixelRatioF=lambda: dpr,
        rhi=lambda: rhi,
    )
    if with_target:
        pixel_size = (
            target_size
            if target_size is not None
            else QSize(int(round(width * dpr)), int(round(height * dpr)))
        )
        host.renderTarget = lambda: SimpleNamespace(pixelSize=lambda: pixel_size)
    return host


class _RecordingCommandBuffer:
    """Captures the one call ``record()`` makes that this file asserts on."""

    def __init__(self) -> None:
        self.viewport: tuple[float, float, float, float] | None = None

    def setGraphicsPipeline(self, pipeline) -> None:
        return None

    def setViewport(self, viewport) -> None:
        self.viewport = tuple(float(v) for v in viewport.viewport())


def _pipeline_ready_pass() -> FilenameOverlayPass:
    """A filename pass that believes it is mounted (no GPU work happens)."""
    filename_pass = FilenameOverlayPass()
    filename_pass._gpu.pipeline = object()  # record() only checks ``is None``
    return filename_pass


# ---------------------------------------------------------------------------
# resolve_target_units: one resolution of the frame's device units
# ---------------------------------------------------------------------------


def test_resolve_target_units_reads_the_backend_correction_and_target_size():
    """Y-down backend: the correction flips y, and the size is device px."""
    from tabs.image_compare.canvas.render_context import resolve_target_units

    rhi = _FakeRhi(y_down_ndc=True)
    clip, fb = resolve_target_units(_host(dpr=2.0, rhi=rhi))

    assert clip == composited_clip_correction(rhi)
    assert clip is not None
    # Column-major mat4 from ``scale(1, -1, 1)``: index 5 is m[1][1].
    assert clip[0] == pytest.approx(1.0)
    assert clip[5] == pytest.approx(-1.0), (
        f"expected the y-down composited correction diag(1, -1, 1, 1), got {clip}"
    )
    assert fb == (1600.0, 1200.0), (
        f"framebuffer_size must be the target's device-px size, got {fb}"
    )


def test_resolve_target_units_is_identity_on_a_y_up_backend():
    """Y-up NDC (GL/D3D): no flip, so the correction is the identity matrix."""
    from tabs.image_compare.canvas.render_context import resolve_target_units

    clip, fb = resolve_target_units(_host(rhi=_FakeRhi(y_down_ndc=False)))

    assert clip == IDENTITY_MATRIX
    assert fb == (800.0, 600.0)


def test_resolve_target_units_reports_no_matrix_before_the_rhi_exists():
    """``rhi() is None`` -> ``None``, never an identity invented locally.

    ``None`` is the legal pre-mount state: the pass that needs a matrix still
    owns its identity fallback (``framing.clip_matrix``), because identity is
    only *correct* on a y-up backend and cannot be decided without the RHI.
    """
    from tabs.image_compare.canvas.render_context import resolve_target_units

    clip, fb = resolve_target_units(_host(dpr=2.0, rhi=None))

    assert clip is None
    assert clip != IDENTITY_MATRIX
    assert fb == (1600.0, 1200.0), (
        "the framebuffer size does not depend on the RHI and must still resolve"
    )


def test_resolve_target_units_falls_back_to_logical_size_times_dpr():
    """No render target (headless/stub host): logical size x DPR, rounded."""
    from tabs.image_compare.canvas.render_context import resolve_target_units

    clip, fb = resolve_target_units(
        _host(dpr=1.5, width=800, height=600, with_target=False)
    )

    assert clip is None
    assert fb == (1200.0, 900.0), f"expected logical x DPR, got {fb}"


def test_resolve_target_units_survives_a_hostile_host():
    """Every query is guarded: a broken target/RHI degrades, never raises.

    This resolver runs inside the per-frame context build, so an exception here
    is a dead canvas -- the whole point of resolving the fallbacks ONCE instead
    of trusting the host.
    """

    from tabs.image_compare.canvas.render_context import resolve_target_units

    def _broken_rhi():
        raise RuntimeError("rhi gone")

    class _BrokenTarget:
        def pixelSize(self):
            raise RuntimeError("target gone")

    host = SimpleNamespace(
        width=lambda: 640,
        height=lambda: 480,
        devicePixelRatioF=lambda: 2.0,
        rhi=_broken_rhi,
        renderTarget=lambda: _BrokenTarget(),
    )

    clip, fb = resolve_target_units(host)

    assert clip is None
    assert fb == (1280.0, 960.0), f"expected the DPR fallback, got {fb}"


# ---------------------------------------------------------------------------
# The context field is the seam: when it is there it wins, when it is not the
# pass keeps working through the SSOT correction.
# ---------------------------------------------------------------------------


def test_context_clip_matrix_field_wins_over_the_backend_correction():
    """A filled ``ctx.clip_matrix`` is authoritative (the engine seam)."""
    ctx = SimpleNamespace(clip_matrix=IDENTITY_MATRIX, framebuffer_size=(800.0, 600.0))

    matrix = framing_clip_matrix(ctx, _FakeRhi(y_down_ndc=True))

    assert matrix == IDENTITY_MATRIX, (
        "the context field must win over composited_clip_correction; otherwise "
        "passes that read the seam (multi_compare) and passes that ask the RHI "
        "can disagree inside one frame"
    )
    assert matrix != composited_clip_correction(_FakeRhi(y_down_ndc=True))


def test_framing_clip_matrix_still_falls_back_to_the_source_correction():
    """Regression, green BEFORE this change: a ctx without the field is fine.

    image_compare's context only gains the field now; every existing pass that
    reads ``ctx.clip_matrix`` (drag_drop_overlay's framing) must keep resolving
    the correction from ``engine/gpu/rt_y_orientation`` until it is filled.
    """
    rhi = _FakeRhi(y_down_ndc=True)
    ctx = SimpleNamespace(width=800, height=600)  # image_compare's pre-change shape

    assert framing_clip_matrix(ctx, rhi) == composited_clip_correction(rhi)


# ---------------------------------------------------------------------------
# ViewportContext: the two fields exist, with defaults, so old call sites work
# ---------------------------------------------------------------------------


def test_viewport_context_fields_default_to_none():
    """Old positional call sites keep working; ``None`` means "no RHI yet"."""
    from tabs.image_compare.canvas.render_context import ViewportContext

    ctx = ViewportContext(
        width=800,
        height=600,
        zoom_level=1.0,
        pan_offset_x=0.0,
        pan_offset_y=0.0,
        is_horizontal=False,
        split_position=0.5,
        canvas_width=800,
        canvas_height=600,
        canvas_offset_x=0.0,
        canvas_offset_y=0.0,
    )

    assert ctx.clip_matrix is None
    assert ctx.framebuffer_size is None


def test_build_render_runtime_context_fills_the_units_without_a_gpu():
    """The real builder fills both fields (or legal Nones) with no window.

    The stub has neither ``rhi()`` nor ``renderTarget()`` -- exactly a headless
    host -- so ``clip_matrix`` must be ``None`` and ``framebuffer_size`` the
    logical fallback; nothing may raise on the way.
    """
    from tabs.image_compare.canvas.render_context import build_render_runtime_context
    from tabs.image_compare.canvas.state import CanvasRuntimeState

    store = SimpleNamespace(
        viewport=SimpleNamespace(
            view_state=SimpleNamespace(
                diff_mode="off",
                is_horizontal=False,
                split_position=0.5,
                split_position_visual=0.5,
                showing_single_image_mode=0,
                channel_view_mode="RGB",
            ),
            render_config=SimpleNamespace(zoom_interpolation_method="BILINEAR"),
        ),
        document=SimpleNamespace(image1_path="left.png", image2_path="right.png"),
        runtime_cache=SimpleNamespace(overlay_clip_rect=None),
    )
    canvas = SimpleNamespace(
        runtime_state=CanvasRuntimeState(_store=store),
        width=lambda: 320,
        height=lambda: 180,
        objectName=lambda: "",
        get_letterbox_params=lambda _slot: (0.0, 0.0, 1.0, 1.0),
    )
    canvas.runtime_state._render_scene = SimpleNamespace(
        blank_white=False,
        single_image_preview=0,
        clip_overlays_to_image_bounds=False,
        is_horizontal=False,
        split_position_visual=0.5,
        overlay_clip_rect=None,
        channel_mode_int=0,
        diff_mode_active=False,
        diff_mode_int=0,
        zoom_interpolation_method="BILINEAR",
        feature_overrides={},
    )

    ctx = build_render_runtime_context(canvas)

    assert ctx.viewport.clip_matrix is None, (
        "no RHI on this host: the builder must not invent an identity matrix"
    )
    assert ctx.viewport.framebuffer_size == (320.0, 180.0), (
        f"expected the logical fallback (DPR 1, no target), got "
        f"{ctx.viewport.framebuffer_size}"
    )


# ---------------------------------------------------------------------------
# filename_overlay: the viewport comes from the render target, like siblings
# ---------------------------------------------------------------------------


def test_filename_overlay_viewport_is_the_render_target_size(qapp):
    """At DPR=2 a 800x600 logical canvas rasterizes into 1600x1200 device px.

    The pass used to rebuild that number as ``ctx.width * dpr``; it must read
    ``renderTarget().pixelSize()`` like guides/capture/divider/magnifier/arcs.
    """
    filename_pass = _pipeline_ready_pass()
    command_buffer = _RecordingCommandBuffer()

    filename_pass.record(
        command_buffer,
        _host(dpr=2.0, rhi=_FakeRhi(y_down_ndc=True)),
        SimpleNamespace(width=800, height=600),
    )

    assert command_buffer.viewport == (0.0, 0.0, 1600.0, 1200.0), (
        f"viewport {command_buffer.viewport} is not the target's pixel size "
        f"(1600x1200 at DPR=2) -- a logical 800x600 viewport draws the raster "
        f"into a quarter of the framebuffer"
    )


def test_filename_overlay_viewport_follows_the_target_not_the_logical_size(qapp):
    """A target whose pixel size disagrees with ``logical x DPR`` is the truth.

    The base pass computed ``ctx.width * dpr``, so an independently resized /
    fractionally scaled target drew the quads through a stale viewport. Here
    the target says 1280x960 while ``800 x 2.0`` says 1600x1200.
    """
    filename_pass = _pipeline_ready_pass()
    command_buffer = _RecordingCommandBuffer()

    filename_pass.record(
        command_buffer,
        _host(dpr=2.0, rhi=_FakeRhi(y_down_ndc=True), target_size=QSize(1280, 960)),
        SimpleNamespace(width=800, height=600),
    )

    assert command_buffer.viewport == (0.0, 0.0, 1280.0, 960.0), (
        f"viewport {command_buffer.viewport} was recomputed from the logical "
        f"size (800 x 2 = 1600x1200) instead of read from "
        f"renderTarget().pixelSize() (1280x960)"
    )


def test_filename_overlay_viewport_keeps_the_device_fallback_without_a_target(qapp):
    """A host with no target still gets device px (the named ``*_device`` path)."""
    filename_pass = _pipeline_ready_pass()
    command_buffer = _RecordingCommandBuffer()

    filename_pass.record(
        command_buffer,
        _host(dpr=2.0, rhi=None, with_target=False),
        SimpleNamespace(width=800, height=600),
    )

    assert command_buffer.viewport == (0.0, 0.0, 1600.0, 1200.0)
