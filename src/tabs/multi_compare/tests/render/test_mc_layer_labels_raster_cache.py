"""Falsification tests for the layer_labels raster cache.

Story: ``LayerLabelsPass.prepare`` used to call ``resolve(ctx)`` (fullscreen
QImage + QPainter + bytes copy) and ``upload_frame`` on EVERY rendered frame
while labels were visible. The cache under test short-circuits both when the
raster inputs are unchanged. These tests prove the counter increments once for
an unchanged ctx and again after any input the signature covers changes, and
that the cache never changes the first-call bytes (parity).
"""

from __future__ import annotations

from types import SimpleNamespace

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage

from tabs.multi_compare.canvas.features.layer_labels import passes
from tabs.multi_compare.models import MultiCompareLabelSettings


class _FakeImage:
    def __init__(self, w: int, h: int) -> None:
        self.shape = (h, w, 3)


class _FakeRU:
    """Stand-in resource-updates sink (the fake shell ignores it)."""


class _FakeShell:
    def __init__(self) -> None:
        self.active = False
        self.quads = 0
        self.clips = 0
        self.uploads = 0
        self.last_frame = None

    def mount(self, rhi, target, shader_dir, shader_stem) -> None:
        return None

    def stage_quad(self, resource_updates) -> None:
        self.quads += 1

    def stage_clip(self, resource_updates, clip_matrix) -> None:
        self.clips += 1

    def upload_frame(self, resource_updates, render_target, frame):
        self.uploads += 1
        self.last_frame = frame
        self.active = frame is not None
        return frame is not None


def _make_composition(*, label_text="a.png", settings=None):
    layer = SimpleNamespace(
        rect=(0, 0, 100, 100),
        label=SimpleNamespace(text=label_text),
        image=_FakeImage(160, 80),
        zoom=1.0,
        pan_y=0.0,
    )
    return SimpleNamespace(
        layers=(layer,),
        canvas_w=100,
        canvas_h=100,
        label_settings=settings,
    )


def _make_ctx(*, composition=None, scale=1.0, offset=(0.0, 0.0), fb=(64.0, 64.0)):
    return SimpleNamespace(
        composition=composition if composition is not None else _make_composition(),
        scale=scale,
        offset=offset,
        framebuffer_size=fb,
        clip_matrix=(1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1),
    )


def _counting_raster(calls, *, image=True):
    def _raster(ctx):
        calls["n"] += 1
        if not image:
            return None
        img = QImage(4, 4, QImage.Format.Format_RGBA8888_Premultiplied)
        img.fill(Qt.GlobalColor.transparent)
        return img

    return _raster


def test_unchanged_ctx_rasterizes_and_uploads_once(monkeypatch, qapp):
    calls = {"n": 0}
    monkeypatch.setattr(passes, "_raster_image", _counting_raster(calls))

    render_pass = passes.LayerLabelsPass()
    shell = _FakeShell()
    render_pass._shell = shell
    ctx = _make_ctx()

    for _ in range(5):
        render_pass.prepare(None, ctx, _FakeRU())

    assert calls["n"] == 1
    assert shell.uploads == 1
    assert shell.active is True
    # Quad + clip are cheap and legitimately camera-dependent: always staged.
    assert shell.quads == 5
    assert shell.clips == 5


def test_label_text_change_invalidates(monkeypatch, qapp):
    calls = {"n": 0}
    monkeypatch.setattr(passes, "_raster_image", _counting_raster(calls))

    render_pass = passes.LayerLabelsPass()
    render_pass._shell = _FakeShell()
    render_pass.prepare(None, _make_ctx(), _FakeRU())
    render_pass.prepare(None, _make_ctx(), _FakeRU())
    assert calls["n"] == 1

    changed = _make_ctx(composition=_make_composition(label_text="b.png"))
    render_pass.prepare(None, changed, _FakeRU())
    assert calls["n"] == 2


def test_scale_and_offset_and_framebuffer_changes_invalidate(monkeypatch, qapp):
    calls = {"n": 0}
    monkeypatch.setattr(passes, "_raster_image", _counting_raster(calls))
    render_pass = passes.LayerLabelsPass()
    render_pass._shell = _FakeShell()

    render_pass.prepare(None, _make_ctx(scale=1.0), _FakeRU())
    assert calls["n"] == 1
    render_pass.prepare(None, _make_ctx(scale=2.0), _FakeRU())
    assert calls["n"] == 2
    render_pass.prepare(None, _make_ctx(scale=2.0, offset=(5.0, 0.0)), _FakeRU())
    assert calls["n"] == 3
    render_pass.prepare(
        None, _make_ctx(scale=2.0, offset=(5.0, 0.0), fb=(128.0, 128.0)), _FakeRU()
    )
    assert calls["n"] == 4


def test_label_settings_change_invalidates(monkeypatch, qapp):
    calls = {"n": 0}
    monkeypatch.setattr(passes, "_raster_image", _counting_raster(calls))
    render_pass = passes.LayerLabelsPass()
    render_pass._shell = _FakeShell()

    render_pass.prepare(None, _make_ctx(composition=_make_composition()), _FakeRU())
    assert calls["n"] == 1
    settings = MultiCompareLabelSettings(font_size_percent=150)
    render_pass.prepare(
        None, _make_ctx(composition=_make_composition(settings=settings)), _FakeRU()
    )
    assert calls["n"] == 2


def test_layer_zoom_and_pan_y_change_invalidates(monkeypatch, qapp):
    calls = {"n": 0}
    monkeypatch.setattr(passes, "_raster_image", _counting_raster(calls))
    render_pass = passes.LayerLabelsPass()
    render_pass._shell = _FakeShell()

    comp = _make_composition()
    render_pass.prepare(None, _make_ctx(composition=comp), _FakeRU())
    assert calls["n"] == 1

    comp.layers[0].pan_y = 0.5
    render_pass.prepare(None, _make_ctx(composition=comp), _FakeRU())
    assert calls["n"] == 2

    comp.layers[0].zoom = 2.0
    render_pass.prepare(None, _make_ctx(composition=comp), _FakeRU())
    assert calls["n"] == 3


def test_none_frame_is_cached_not_recomputed(monkeypatch, qapp):
    calls = {"n": 0}
    monkeypatch.setattr(passes, "_raster_image", _counting_raster(calls, image=False))
    render_pass = passes.LayerLabelsPass()
    shell = _FakeShell()
    render_pass._shell = shell

    for _ in range(3):
        render_pass.prepare(None, _make_ctx(), _FakeRU())

    assert calls["n"] == 1
    assert shell.uploads == 1
    assert shell.active is False


def test_first_upload_matches_independent_resolve(qapp):
    """The cached path must not change the first-call bytes (parity)."""
    render_pass = passes.LayerLabelsPass()
    shell = _FakeShell()
    render_pass._shell = shell
    ctx = _make_ctx(fb=(256.0, 256.0), offset=(3.0, 7.0))

    expected = passes.resolve(ctx)
    render_pass.prepare(None, ctx, _FakeRU())

    assert expected is not None and expected[2]
    assert shell.last_frame == expected


def test_remount_forces_reupload(monkeypatch, qapp):
    calls = {"n": 0}
    monkeypatch.setattr(passes, "_raster_image", _counting_raster(calls))
    render_pass = passes.LayerLabelsPass()
    render_pass._shell = _FakeShell()
    ctx = _make_ctx()
    render_pass.prepare(None, ctx, _FakeRU())
    assert calls["n"] == 1

    # initialize()/mount() owns a fresh placeholder texture; the cache must
    # be dropped so the next prepare re-uploads.
    render_pass.initialize(None, None)
    render_pass.prepare(None, ctx, _FakeRU())
    assert calls["n"] == 2


def test_raster_signature_is_pure_and_value_based():
    ctx = _make_ctx()
    assert passes.raster_signature(ctx) == passes.raster_signature(ctx)
    assert passes.raster_signature(_make_ctx(scale=1.0)) != passes.raster_signature(
        _make_ctx(scale=2.0)
    )
