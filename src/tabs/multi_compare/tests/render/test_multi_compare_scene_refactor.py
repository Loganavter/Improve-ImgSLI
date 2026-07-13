"""Multi Compare scene rendering stays split into widget, renderer, and passes."""

from pathlib import Path
from types import SimpleNamespace

from tabs.multi_compare.scene.passes import (
    BaseImagesPass,
    DragDropOverlaySource,
)
from tabs.multi_compare.scene.passes import base_images as base_images_module


def test_multi_compare_canvas_widget_does_not_own_qrhi_rendering_resources():
    source = Path("src/tabs/multi_compare/ui/canvas_widget.py").read_text(
        encoding="utf-8"
    )

    forbidden = [
        "QRhiBuffer",
        "QRhiGraphicsPipeline",
        "QRhiShaderResourceBinding",
        "QRhiShaderStage",
        "QRhiTexture",
        "QRhiViewport",
        "newGraphicsPipeline",
        "newShaderResourceBindings",
        "newTexture",
    ]
    assert not any(token in source for token in forbidden)


def test_multi_compare_gpu_export_uses_same_widget_renderer_path():
    source = Path("src/tabs/multi_compare/services/gpu_export.py").read_text(
        encoding="utf-8"
    )

    assert "MultiCompareCanvasWidget" in source
    assert "apply_canvas_render_plan(widget, render_plan)" in source
    assert "widget.grabFramebuffer()" in source
    assert "widget.set_state(" not in source
    assert "build_composition_plan" not in source


def test_multi_compare_drag_overlay_is_live_only_by_state():
    source = DragDropOverlaySource()

    assert source.should_paint(None, SimpleNamespace(drag_active=False)) is False
    assert source.should_paint(None, SimpleNamespace(drag_active=True)) is True


def test_multi_compare_base_image_pass_reuses_slot_srb_until_texture_changes(
    monkeypatch,
):
    created_srbs = []

    class _FakeStageFlag:
        VertexStage = 1
        FragmentStage = 2

    class _FakeBinding:
        StageFlag = _FakeStageFlag

        @staticmethod
        def uniformBuffer(*args):
            return ("uniform", args)

        @staticmethod
        def sampledTexture(*args):
            return ("texture", args)

    class _FakeSrb:
        def __init__(self):
            self.destroyed = False
            created_srbs.append(self)

        def setBindings(self, bindings):
            self.bindings = bindings

        def create(self):
            return True

        def destroy(self):
            self.destroyed = True

    class _FakeRhi:
        def newShaderResourceBindings(self):
            return _FakeSrb()

    monkeypatch.setattr(base_images_module, "QRhiShaderResourceBinding", _FakeBinding)

    render_pass = BaseImagesPass()
    texture_a = object()
    render_pass.slot_textures[1] = texture_a
    render_pass.slot_uniform_buffers.append(object())
    renderer = SimpleNamespace(rhi=_FakeRhi(), sampler=object())

    first_bound = render_pass._ensure_tile_srb(renderer, 0, 1, texture_a)

    assert render_pass._ensure_tile_srb(renderer, 0, 1, texture_a) is first_bound

    texture_b = object()
    render_pass.slot_textures[1] = texture_b
    second_bound = render_pass._ensure_tile_srb(renderer, 0, 1, texture_b)

    assert second_bound is not first_bound
    assert first_bound.destroyed is True
