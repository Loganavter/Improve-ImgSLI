"""Export DPR units: one device-px answer for the Multi Compare tiled export.

The defect these tests pin (measured before the fix, canvas 3000x2000, one
composition layer):

=====================  ======================  ============  ===============
DPR                    framebuffer             composition   frame area
                                               covers        covered
=====================  ======================  ============  ===============
1.0                    3000x2000               3000x2000     1.0
1.5                    4500x3000               3000x2000     0.4444
2.0                    6000x4000               3000x2000     0.25
=====================  ======================  ============  ===============

The tiled exporter sized its offscreen widget in *logical* output px, so the
framebuffer was DPR times larger, while the export viewport handed to
``build_render_context`` stayed in output (logical) px. The projection scaled
the composition by ``min(full_frame_fb / canvas)`` in framebuffer px, so the
composition occupied the top-left ``1/DPR²`` of the grabbed frame — and
``export_tiling`` then quietly bilinear-resized that device-pixel grab down to
the logical tile, which is why the export "worked" while shipping a quarter
frame.

The invariant: **one export framebuffer px is one output px**
(``export_surface_size`` + ``fit_framebuffer_to_target=True``), the projection
works only in framebuffer px (``framebuffer_size`` = ``target.pixelSize()``),
and a grab that does not cover its target is loud (crop of the sub-logical-px
rounding, else ``ExportFramebufferMismatch``) — never a silent resample.
"""

from __future__ import annotations

import pytest
from PIL import Image
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication, QWidget

from engine.gpu.export_tiling import (
    ExportFramebufferMismatch,
    TiledFramebufferExporter,
    export_framebuffer_scale,
    export_surface_size,
    iter_export_tile_rects,
    resolve_export_framebuffer,
)
from tabs.multi_compare.scene.projection import (
    build_render_context,
    composition_frame_geometry,
    letterbox_uv,
)
from ui.canvas_presentation.composition import (
    CompositionPlan,
    LayerNode,
    resolve_composition,
)

CANVAS = (900, 400)
TILE_EXTENT = 500
DPRS = (1.0, 1.25, 1.5, 2.0)


def _tiles() -> list[tuple[int, int, int, int]]:
    """The tiled path's tile rects in output px (uniform grid per max extent)."""
    return list(iter_export_tile_rects(CANVAS[0], CANVAS[1], TILE_EXTENT))


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class _DprCanvas(QWidget):
    """Offscreen surface whose framebuffer is ``size * devicePixelRatioF()``.

    That is Qt's contract for a ``QRhiWidget`` render target
    (``target.pixelSize()``); ``grab_scale`` simulates a surface that breaks it
    (the units defect, or a mid-export DPR change) so the guard is falsifiable.
    """

    def __init__(self, dpr: float, *, grab_scale: float | None = None) -> None:
        super().__init__()
        self._dpr = float(dpr)
        self._grab_scale = self._dpr if grab_scale is None else float(grab_scale)
        self.logical_sizes: list[tuple[int, int]] = []
        self.prepare_calls = 0
        self._export_canvas_viewport = None

    # Qt names (N802)
    def devicePixelRatioF(self) -> float:  # noqa: N802
        return self._dpr

    def framebuffer_size(self) -> tuple[int, int]:
        return (
            int(round(self.width() * self._grab_scale)),
            int(round(self.height() * self._grab_scale)),
        )

    def resize(self, *args) -> None:  # type: ignore[override]
        super().resize(*args)
        size = args[0] if len(args) == 1 else args
        width = size.width() if hasattr(size, "width") else int(size[0])
        height = size.height() if hasattr(size, "height") else int(size[1])
        self.logical_sizes.append((int(width), int(height)))

    def grabFramebuffer(self) -> QImage:  # noqa: N802
        width, height = self.framebuffer_size()
        image = QImage(width, height, QImage.Format.Format_RGBA8888)
        image.fill(0xFF102030)
        return image


def _composition(width: int = CANVAS[0], height: int = CANVAS[1]):
    return resolve_composition(
        CompositionPlan(
            root=LayerNode(layer_id=1, image=None, zoom=1.0),
            canvas_w=width,
            canvas_h=height,
        )
    )


def _tiled_export(widget: _DprCanvas) -> tuple[dict, Image.Image]:
    """Run one tiled export, recording the first tile's viewport + grab size."""
    captured: dict = {}

    def set_viewport(viewport):
        widget._export_canvas_viewport = viewport
        if viewport is not None and "viewport" not in captured:
            captured["viewport"] = viewport
            captured["grab_size"] = widget.framebuffer_size()

    exporter = TiledFramebufferExporter(
        widget,
        set_export_viewport=set_viewport,
        prepare_frame=lambda: setattr(widget, "prepare_calls", widget.prepare_calls + 1),
        query_max_texture_size=lambda: TILE_EXTENT,
        fit_framebuffer_to_target=True,
    )
    image = exporter.render_rgba(*CANVAS, max_extent=TILE_EXTENT)
    return captured, image


def test_export_surface_size_is_the_one_device_px_answer(qapp):
    """``ceil(target / dpr)`` logical px: framebuffer covers target, overload < dpr."""
    for dpr in DPRS:
        widget = _DprCanvas(dpr)
        for target in ((4096, 4096), (500, 400), (3001, 1999)):
            logical = export_surface_size(widget, target)
            device = (logical[0] * dpr, logical[1] * dpr)
            assert device[0] >= target[0] and device[1] >= target[1]
            assert device[0] - target[0] < dpr
            assert device[1] - target[1] < dpr
        assert export_framebuffer_scale(widget) == dpr


@pytest.mark.parametrize("dpr", DPRS)
def test_tiled_export_grab_is_one_to_one_and_fills_the_frame(qapp, dpr):
    """Every tiled grab is the output tile (1:1) and the composition fills it."""
    widget = _DprCanvas(dpr)
    captured, image = _tiled_export(widget)

    assert image.size == CANVAS
    viewport = captured["viewport"]
    assert viewport == (CANVAS[0], CANVAS[1], 0, 0)
    grab_size = captured["grab_size"]
    first_left, first_top, first_w, first_h = _tiles()[0]
    tile = (first_w, first_h)
    # One framebuffer px == one output px (only sub-logical-px rounding surplus).
    assert grab_size[0] >= tile[0] and grab_size[0] - tile[0] < dpr
    assert grab_size[1] >= tile[1] and grab_size[1] - tile[1] < dpr

    widget._export_canvas_viewport = viewport  # render_rgba clears it at the end
    ctx = build_render_context(
        composition=_composition(),
        # The renderer's framebuffer_size is target.pixelSize().
        framebuffer_size=tuple(float(v) for v in grab_size),
        clip_matrix=(),
        available_slot_ids=frozenset({1}),
        widget=widget,
    )

    # Geometry is in framebuffer px on both sides: the composition is the full
    # frame (scale 1), not a 1/DPR² corner.
    assert ctx.scale == pytest.approx(1.0)
    assert ctx.offset == pytest.approx((0.0, 0.0))
    assert ctx.projected_layers[0].rect_fb == pytest.approx(
        (0.0, 0.0, float(CANVAS[0]), float(CANVAS[1]))
    )
    # How many DEVICE px the grab spends per output px it represents. Pre-fix
    # this was the DPR (the grab was a supersampled logical tile), so the
    # composition covered only 1/DPR² of the real device frame — 0.25 at DPR 2.
    device_per_output = (grab_size[0] / tile[0], grab_size[1] / tile[1])
    assert device_per_output == pytest.approx((1.0, 1.0), abs=0.01)
    frame_device = (viewport[0] * device_per_output[0], viewport[1] * device_per_output[1])
    covered = (CANVAS[0] * ctx.scale * CANVAS[1] * ctx.scale) / (
        frame_device[0] * frame_device[1]
    )
    assert covered == pytest.approx(1.0)

    uv = letterbox_uv(
        framebuffer_size=ctx.framebuffer_size,
        scale=ctx.scale,
        offset=ctx.offset,
        canvas_size=(float(CANVAS[0]), float(CANVAS[1])),
    )
    # The (0,0) tile starts at the frame origin; the composition spans it fully
    # vertically and extends past the tile horizontally (a crop, not a shrink).
    assert uv[0] == pytest.approx(0.0)
    assert uv[1] == pytest.approx(0.0)
    assert uv[2] == pytest.approx(CANVAS[0] / tile[0])
    assert uv[3] == pytest.approx(1.0, abs=1e-3)


@pytest.mark.parametrize("dpr", DPRS)
def test_full_frame_letterbox_covers_unit_uv(qapp, dpr):
    """A full-frame export viewport covers 0..1 uv on both axes at any DPR."""
    widget = _DprCanvas(dpr)
    widget._export_canvas_viewport = (CANVAS[0], CANVAS[1], 0, 0)
    fb = export_surface_size(widget, CANVAS)
    fb = (fb[0] * dpr, fb[1] * dpr)
    ctx = build_render_context(
        composition=_composition(),
        framebuffer_size=(float(fb[0]), float(fb[1])),
        clip_matrix=(),
        available_slot_ids=frozenset({1}),
        widget=widget,
    )
    uv = letterbox_uv(
        framebuffer_size=ctx.framebuffer_size,
        scale=ctx.scale,
        offset=ctx.offset,
        canvas_size=(float(CANVAS[0]), float(CANVAS[1])),
    )
    assert ctx.scale == pytest.approx(1.0)
    assert uv[0] == pytest.approx(0.0)
    assert uv[1] == pytest.approx(0.0)
    # 0..1 on both axes, up to the sub-logical-px rounding of the surface size
    # (pre-fix this was 1/DPR: 0.5 at DPR 2, 0.667 at DPR 1.5).
    assert uv[2] == pytest.approx(1.0, abs=0.01)
    assert uv[3] == pytest.approx(1.0, abs=0.01)


def test_composition_frame_geometry_is_single_space():
    """Frame and tile origin are ONE space — the tile origin is a plain offset."""
    canvas = (3000.0, 2000.0)
    frame = (1000.0, 1000.0)
    scale, ox, oy = composition_frame_geometry(canvas_size=canvas, frame_size=frame)
    assert canvas[0] * scale <= frame[0] and canvas[1] * scale <= frame[1]
    assert canvas[0] * scale == pytest.approx(frame[0])  # width-bound letterbox
    assert scale == pytest.approx(1.0 / 3.0)
    assert ox == pytest.approx(0.0)
    assert oy == pytest.approx((frame[1] - canvas[1] * scale) * 0.5)

    scale_tiled, ox_tiled, oy_tiled = composition_frame_geometry(
        canvas_size=canvas, frame_size=frame, tile_origin=(300.0, 40.0)
    )
    assert scale_tiled == scale
    assert ox_tiled == pytest.approx(ox - 300.0)
    assert oy_tiled == pytest.approx(oy - 40.0)


@pytest.mark.parametrize("dpr", (1.5, 2.0))
def test_tiled_export_never_resamples(qapp, dpr, monkeypatch):
    """A DPR-fitted grab is used 1:1 — no bilinear step anywhere."""

    def _forbidden(*_args, **_kwargs):
        raise AssertionError("silent resample of a device-pixel export grab")

    monkeypatch.setattr(Image.Image, "resize", _forbidden)
    widget = _DprCanvas(dpr)
    image = _tiled_export(widget)[1]
    assert image.size == CANVAS
    # The surface is sized in LOGICAL px (not the output px), which is what makes
    # the grab 1:1 instead of a DPR-supersampled frame.
    assert widget.logical_sizes
    assert widget.logical_sizes[0][0] < CANVAS[0]
    assert widget.logical_sizes[0] == export_surface_size(widget, _tiles()[0][2:])


@pytest.mark.parametrize(
    "grab_scale", (1.0, 4.0), ids=("framebuffer-smaller", "framebuffer-supersampled")
)
def test_grab_mismatch_is_loud_not_resampled(qapp, grab_scale):
    """A grab that cannot be cropped to the target raises, never resamples."""
    widget = _DprCanvas(2.0, grab_scale=grab_scale)
    with pytest.raises(ExportFramebufferMismatch):
        _tiled_export(widget)


def test_resolve_export_framebuffer_modes():
    assert resolve_export_framebuffer((500, 400), (500, 400), scale=2.0, fit_framebuffer=True) == "exact"
    # Sub-logical-pixel rounding surplus of export_surface_size: crop, lossless.
    assert resolve_export_framebuffer((501, 400), (500, 400), scale=2.0, fit_framebuffer=True) == "crop"
    with pytest.raises(ExportFramebufferMismatch):
        resolve_export_framebuffer((1000, 800), (500, 400), scale=2.0, fit_framebuffer=True)
    with pytest.raises(ExportFramebufferMismatch):
        resolve_export_framebuffer((250, 200), (500, 400), scale=2.0, fit_framebuffer=True)
    # Legacy logical-space surface (image_compare export): explicit downscale.
    assert resolve_export_framebuffer((1000, 800), (500, 400), scale=2.0, fit_framebuffer=False) == "resample"


def test_legacy_logical_surface_still_downscales_explicitly(qapp):
    """Default (image_compare) shape keeps its downscale — logged, not silent."""
    widget = _DprCanvas(2.0)
    exporter = TiledFramebufferExporter(
        widget,
        set_export_viewport=lambda _vp: None,
        prepare_frame=lambda: None,
        query_max_texture_size=lambda: TILE_EXTENT,
    )
    image = exporter._render_single(*CANVAS)
    assert image.size == CANVAS
    # Legacy sizing is logical px == output px (the scene is logical-space),
    # so the framebuffer is a 2x supersample that is downscaled once.
    assert widget.logical_sizes[0] == CANVAS
    assert widget.framebuffer_size() == (CANVAS[0] * 2, CANVAS[1] * 2)


@pytest.mark.parametrize(
    ("dpr", "canvas"),
    ((2.0, CANVAS), (1.5, (902, 402))),
    ids=("dpr2-exact-grab", "dpr1.5-rounding-crop"),
)
def test_mc_single_frame_export_is_one_to_one(qapp, monkeypatch, dpr, canvas):
    """MC's own (non-tiled) path sizes the surface by DPR too, no QImage.scale."""
    from tabs.multi_compare.services import gpu_export as gpu_export_module

    widget = _DprCanvas(dpr)
    widget.rhi = lambda: object()
    monkeypatch.setattr(
        "ui.canvas_infra.rhi.rhi_backend.query_max_texture_size", lambda _rhi: 4096
    )
    monkeypatch.setattr(
        gpu_export_module, "apply_canvas_render_plan", lambda *_a, **_k: None
    )
    exporter = gpu_export_module.MultiCompareGpuExporter()
    monkeypatch.setattr(exporter, "_ensure_widget", lambda: widget)

    qimage = exporter.render_to_qimage(
        _composition_plan(*canvas),
        output_w=canvas[0],
        output_h=canvas[1],
        background_color=None,
        fill_background=False,
    )
    assert (qimage.width(), qimage.height()) == canvas
    assert widget.logical_sizes[0] == export_surface_size(widget, canvas)
    assert widget.logical_sizes[0] != canvas  # logical px, not output px
    if dpr == 2.0:
        assert widget.logical_sizes[0] == (canvas[0] // 2, canvas[1] // 2)
    else:
        # ceil() overshoots by <1 logical px on this width: the grab is cropped.
        assert widget.framebuffer_size() != canvas


def test_mc_tiled_path_requests_dpr_fitted_framebuffer(qapp, monkeypatch):
    """The tiled path opts into the one-device-px-per-output-px surface."""
    from types import SimpleNamespace

    from tabs.multi_compare.services import gpu_export as gpu_export_module

    captured: dict = {}

    class _FakeExporter:
        def __init__(self, widget, **kwargs):
            captured.update(kwargs)
            self._last_size = None

        def render_rgba(self, canvas_w, canvas_h, *, max_extent=4096):
            return Image.new("RGBA", (canvas_w, canvas_h), (1, 2, 3, 255))

    monkeypatch.setattr(gpu_export_module, "TiledFramebufferExporter", _FakeExporter)
    monkeypatch.setattr(
        "ui.canvas_infra.rhi.rhi_backend.query_max_texture_size", lambda _rhi: 4096
    )
    widget = SimpleNamespace(rhi=lambda: object())
    exporter = gpu_export_module.MultiCompareGpuExporter()
    monkeypatch.setattr(exporter, "_ensure_widget", lambda: widget)

    exporter.render_to_qimage(
        _composition_plan(),
        output_w=9000,
        output_h=5000,
        background_color=None,
        fill_background=False,
    )
    assert captured["fit_framebuffer_to_target"] is True


def _composition_plan(width: int = CANVAS[0], height: int = CANVAS[1]) -> CompositionPlan:
    return CompositionPlan(
        root=LayerNode(layer_id=1, image=None, zoom=1.0),
        canvas_w=width,
        canvas_h=height,
    )
