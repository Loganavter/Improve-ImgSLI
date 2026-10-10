"""GPU-resource reuse for the filename-overlay downsample stage.

Falsification story (bug): the label width is clamped to the split line
(``ui.canvas_presentation.filename_labels.label_rects``), and ``rw``/``rh``
are part of the raster cache key in ``FilenameOverlayPass.prepare``. Dragging
the divider therefore changed the key every frame, and
``FilenameOverlayGpuResources.ensure_slot_textures`` rebuilt not just the
textures but the downsample render-pass descriptor, render target and
graphics pipeline -- a per-mouse-move driver stall.

Fix: the downsample rpdesc + graphics pipeline depend only on the shaders,
vertex layout, topology and the (format-based) rpdesc -- never on texture
size -- so they are created ONCE and reused; only the textures, SRBs and
render target follow the size. This test drives ``ensure_slot_textures``
through two size changes with a fake QRhi and asserts the pipeline and
rpdesc are created once while the target is rebuilt per size.
"""

from __future__ import annotations

from types import SimpleNamespace

from PySide6.QtCore import QSize

import tabs.image_compare.canvas.features.filename_overlay.render.gpu_resources as g


class _FakeTexture:
    def create(self) -> bool:
        return True

    def destroy(self) -> None:
        pass


class _FakeSRB:
    def setBindings(self, bindings) -> None:
        self._bindings = bindings

    def create(self) -> bool:
        return True

    def destroy(self) -> None:
        pass


class _FakePipeline:
    def setShaderStages(self, stages) -> None:
        self._stages = stages

    def setTopology(self, topology) -> None:
        pass

    def setRenderPassDescriptor(self, rpdesc) -> None:
        self._rpdesc = rpdesc

    def setShaderResourceBindings(self, srb) -> None:
        self._srb = srb

    def create(self) -> bool:
        return True


class _FakeTarget:
    def __init__(self, rhi) -> None:
        self._rhi = rhi

    def newCompatibleRenderPassDescriptor(self):
        self._rhi.rpdesc_count += 1
        return object()

    def setRenderPassDescriptor(self, rpdesc) -> None:
        self._rpdesc = rpdesc

    def create(self) -> bool:
        return True

    def destroy(self) -> None:
        pass


class _FakeRhi:
    def __init__(self) -> None:
        self.pipeline_count = 0
        self.rpdesc_count = 0
        self.target_count = 0

    def newTexture(self, *args, **kwargs):
        return _FakeTexture()

    def newShaderResourceBindings(self):
        return _FakeSRB()

    def newTextureRenderTarget(self, description):
        self.target_count += 1
        return _FakeTarget(self)

    def newGraphicsPipeline(self):
        self.pipeline_count += 1
        return _FakePipeline()


def _patch_qrhi(monkeypatch) -> None:
    monkeypatch.setattr(g, "QRhiColorAttachment", lambda texture: texture)
    monkeypatch.setattr(
        g, "QRhiTextureRenderTargetDescription", lambda attachment: attachment
    )
    monkeypatch.setattr(
        g,
        "QRhiShaderResourceBinding",
        SimpleNamespace(
            StageFlag=SimpleNamespace(VertexStage=0, FragmentStage=0),
            uniformBuffer=lambda *a, **k: None,
            sampledTexture=lambda *a, **k: None,
        ),
    )
    class _FakeShaderStage:
        Type = SimpleNamespace(Vertex=0, Fragment=0)

        def __init__(self, *args, **kwargs) -> None:
            pass

    monkeypatch.setattr(g, "QRhiShaderStage", _FakeShaderStage)
    monkeypatch.setattr(
        g,
        "QRhiGraphicsPipeline",
        SimpleNamespace(Topology=SimpleNamespace(Triangles=0)),
    )
    monkeypatch.setattr(
        g,
        "QRhiTexture",
        SimpleNamespace(
            Format=SimpleNamespace(RGBA8=0),
            Flag=SimpleNamespace(RenderTarget=1),
        ),
    )
    monkeypatch.setattr(g, "load_qshader", lambda *a, **k: object())


def test_ensure_slot_textures_creates_pipeline_and_rpdesc_once(monkeypatch):
    _patch_qrhi(monkeypatch)
    gpu = g.FilenameOverlayGpuResources()
    fake = _FakeRhi()
    gpu.rhi = fake
    gpu.uniform_buffer = object()
    gpu.sampler_linear = object()
    gpu.sampler_nearest = object()
    slot = gpu.slots[0]

    gpu.ensure_slot_textures(slot, QSize(80, 8), QSize(20, 2))
    pipeline = slot.downsample_pipeline
    rpdesc = slot.downsample_rpdesc
    assert pipeline is not None and rpdesc is not None

    # Second call at a different size (what a divider drag does every frame).
    gpu.ensure_slot_textures(slot, QSize(160, 8), QSize(40, 2))

    assert slot.downsample_pipeline is pipeline, (
        "downsample pipeline was recreated on a size change -- QRhi pipelines "
        "are size-independent and must be reused"
    )
    assert slot.downsample_rpdesc is rpdesc, (
        "downsample rpdesc was recreated on a size change -- it is "
        "format-based and must be reused"
    )
    assert fake.pipeline_count == 1, (
        f"newGraphicsPipeline called {fake.pipeline_count} times for one slot "
        "across two sizes; must be exactly 1"
    )
    assert fake.rpdesc_count == 1, (
        f"newCompatibleRenderPassDescriptor called {fake.rpdesc_count} times; "
        "must be exactly 1"
    )
    assert fake.target_count == 2, (
        "the render target must still be rebuilt per texture size (it wraps "
        "the texture), but nothing heavier should be"
    )
