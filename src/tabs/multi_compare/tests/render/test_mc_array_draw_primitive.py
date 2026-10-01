"""MC base pass array branch routes through the shared engine primitive.

Regression for the engine-tiled-view extraction: ``BaseImagesPass.record``
must issue exactly one instanced ``draw(4, instance_count)`` through
``engine.gpu.array_draw.draw_array_instances`` (no manual
pipeline/viewport/vertex-input/SRB sequence left in the tab), keep its
early-return guard, and stay off the plain path when the array path is
selected. Fakes only, no GPU.
"""

from __future__ import annotations

from types import SimpleNamespace

from tabs.multi_compare.scene.passes.base_images import BaseImagesPass


class _FakeArrayResources:
    def __init__(self, *, pipeline="array-pipeline") -> None:
        self.array_pipeline = pipeline
        self.array_instance_buffer = "array-ibuf"
        self.ensure_calls: list = []

    def ensure_array_srb(self, sampler_name):
        self.ensure_calls.append(sampler_name)
        return "array-srb"


class _FakeCommandBuffer:
    def __init__(self) -> None:
        self.calls: list = []
        self.last_viewport = None
        self.last_bindings = None

    def setGraphicsPipeline(self, pipeline) -> None:
        self.calls.append("setGraphicsPipeline")

    def setViewport(self, viewport) -> None:
        self.calls.append("setViewport")
        self.last_viewport = viewport

    def setVertexInput(self, start, bindings) -> None:
        self.calls.append("setVertexInput")
        self.last_bindings = (start, list(bindings))

    def setShaderResources(self, srb) -> None:
        self.calls.append("setShaderResources")

    def draw(self, vertices, instance_count=None) -> None:
        self.calls.append(("draw", vertices, instance_count))


def _array_pass(*, instance_count=5, pipeline="array-pipeline"):
    rp = BaseImagesPass()
    rp._use_array_this_frame = True
    rp.array_draw_instance_count = instance_count
    rp.array_resources = _FakeArrayResources(pipeline=pipeline)
    rp.slot_resources = SimpleNamespace(slot_vertex_buffers=["slot-vbo"])
    return rp


def _ctx():
    return SimpleNamespace(
        projected_layers=[object()], framebuffer_size=(800, 600)
    )


def test_array_branch_issues_one_instanced_draw_with_instance_count():
    rp = _array_pass(instance_count=5)
    cmd = _FakeCommandBuffer()

    rp.record(cmd, SimpleNamespace(), _ctx())

    assert cmd.calls == [
        "setGraphicsPipeline",
        "setViewport",
        "setVertexInput",
        "setShaderResources",
        ("draw", 4, 5),
    ]
    assert cmd.last_viewport.viewport() == [0.0, 0.0, 800.0, 600.0]
    assert cmd.last_bindings == (0, [("slot-vbo", 0), ("array-ibuf", 0)])
    assert rp.array_resources.ensure_calls == ["default"]


def test_array_branch_skips_draw_when_instance_count_zero():
    rp = _array_pass(instance_count=0)
    cmd = _FakeCommandBuffer()

    rp.record(cmd, SimpleNamespace(), _ctx())

    assert cmd.calls == []
    assert rp.array_resources.ensure_calls == []


def test_array_branch_skips_draw_when_pipeline_missing():
    rp = _array_pass(pipeline=None)
    cmd = _FakeCommandBuffer()

    rp.record(cmd, SimpleNamespace(), _ctx())

    assert cmd.calls == []
    assert rp.array_resources.ensure_calls == []
