"""Unit tests for the shared texture-array instanced-draw core.

Covers the per-instance packing layout/offsets, the layer2 round-trip, the
layer-pixel helper, and the exact ordered QRhi calls ``record_array_draw``
makes (including the empty-instance begin/end pass pair with no draw).
"""

from __future__ import annotations

import struct
from types import SimpleNamespace

from engine.gpu.array_draw import (
    ARRAY_INSTANCE_ATTRIBUTES,
    ARRAY_INSTANCE_FMT,
    ARRAY_INSTANCE_STRIDE,
    ArrayInstance,
    array_layer_px,
    draw_array_instances,
    pack_array_instance,
    record_array_draw,
    unpack_instance_layer2,
)

_LAYERS_OFFSET = struct.calcsize("<4f4f4f2f")
_BBOX_OFFSET = struct.calcsize("<4f4f4f2f3i")


def _inst(
    layer1: int = 1,
    layer2: int = 2,
    layer_diff: int = 0,
    bbox: tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0),
) -> ArrayInstance:
    return ArrayInstance(
        rect1=(0.0, 0.0, 0.5, 1.0),
        rect2=(0.5, 0.0, 0.5, 1.0),
        content_scale=(1.0, 1.0, 1.0, 1.0),
        content_scale_diff=(1.0, 1.0),
        layer1=layer1,
        layer2=layer2,
        layer_diff=layer_diff,
        bbox=bbox,
    )


def test_pack_stride_format_and_attribute_offsets():
    blob = pack_array_instance(_inst(layer1=3, layer2=7))
    assert len(blob) == ARRAY_INSTANCE_STRIDE == 100
    assert struct.calcsize(ARRAY_INSTANCE_FMT) == ARRAY_INSTANCE_STRIDE
    assert (3, 7, 0) == struct.unpack_from("<3i", blob, _LAYERS_OFFSET)
    assert [a.offset() for a in ARRAY_INSTANCE_ATTRIBUTES] == [0, 16, 32, 48, 56, 68, 84]
    assert [a.binding() for a in ARRAY_INSTANCE_ATTRIBUTES] == [1] * 7


def test_unpack_layer2_roundtrip():
    blob = b"".join(
        pack_array_instance(_inst(l1, l2)) for l1, l2 in [(3, 7), (3, 5), (0, 4)]
    )
    assert len(blob) == 3 * ARRAY_INSTANCE_STRIDE
    assert [unpack_instance_layer2(blob, i) for i in range(3)] == [7, 5, 4]


def test_pack_legacy_kwargs_matches_instance():
    via_instance = pack_array_instance(_inst(layer1=3, layer2=7))
    via_kwargs = pack_array_instance(
        rect1=(0.0, 0.0, 0.5, 1.0),
        rect2=(0.5, 0.0, 0.5, 1.0),
        content_scale=(1.0, 1.0, 1.0, 1.0),
        content_scale_diff=(1.0, 1.0),
        layer1=3,
        layer2=7,
        layer_diff=0,
        bbox=(0.0, 0.0, 1.0, 1.0),
    )
    assert via_instance == via_kwargs


def test_array_layer_px_adds_two_aprons():
    assert array_layer_px(512, 8) == 528
    assert array_layer_px(64, 0) == 64


class _FakeResources:
    def __init__(self) -> None:
        self.array_pipeline = "pipeline"
        self.array_uniform_buffer = "ubuf"
        self.array_instance_buffer = "ibuf"
        self.calls: list = []
        # Mirrors TileArrayResourcesBase: the SRB cache is idempotent per
        # sampler name, so the pre-pass ensure plus the draw-time re-ensure
        # inside ``draw_array_instances`` only log once.
        self._srb_cache: dict = {}

    def ensure_array_pipeline(self, target) -> None:
        self.calls.append(("ensure_pipeline", target))

    def ensure_array_instance_capacity(self, count: int) -> None:
        self.calls.append(("ensure_capacity", count))

    def ensure_array_srb(self, sampler_name: str):
        cached = self._srb_cache.get(sampler_name)
        if cached is not None:
            return cached
        self.calls.append(("ensure_srb", sampler_name))
        srb = "srb"
        self._srb_cache[sampler_name] = srb
        return srb


class _FakeUpdates:
    def __init__(self) -> None:
        self.writes: list = []

    def updateDynamicBuffer(self, buffer, offset, data) -> None:
        self.writes.append((buffer, offset, data))


class _FakeCommandBuffer:
    def __init__(self) -> None:
        self.calls: list = []
        self.last_viewport = None
        self.last_bindings = None
        self.last_srb = None

    def beginPass(self, *args) -> None:
        self.calls.append("beginPass")

    def setGraphicsPipeline(self, pipeline) -> None:
        self.calls.append("setGraphicsPipeline")

    def setViewport(self, viewport) -> None:
        self.calls.append("setViewport")
        self.last_viewport = viewport

    def setVertexInput(self, start, bindings) -> None:
        self.calls.append("setVertexInput")
        self.last_bindings = (start, bindings)

    def setShaderResources(self, srb) -> None:
        self.calls.append("setShaderResources")
        self.last_srb = srb

    def draw(self, vertices, instance_count) -> None:
        self.calls.append(("draw", vertices, instance_count))

    def endPass(self) -> None:
        self.calls.append("endPass")


def _target():
    return SimpleNamespace(
        pixelSize=lambda: SimpleNamespace(width=lambda: 10, height=lambda: 20)
    )


def test_record_array_draw_orders_calls_and_draws_once():
    resources = _FakeResources()
    updates = _FakeUpdates()
    command_buffer = _FakeCommandBuffer()
    pre_begin: list = []
    in_pass: list = []
    instances = [_inst(1, 2), _inst(3, 4)]

    target = _target()
    record_array_draw(
        command_buffer,
        resources=resources,
        vertex_buffer="vbo",
        instances=instances,
        uniform_bytes=b"U" * 8,
        target=target,
        clear_color="clear",
        updates=updates,
        pre_begin=lambda: pre_begin.append("pre"),
        in_pass=lambda: in_pass.append("in"),
    )

    assert pre_begin == ["pre"]
    assert in_pass == ["in"]
    assert command_buffer.calls == [
        "beginPass",
        "setGraphicsPipeline",
        "setViewport",
        "setVertexInput",
        "setShaderResources",
        ("draw", 4, 2),
        "endPass",
    ]
    assert resources.calls == [
        ("ensure_pipeline", target),
        ("ensure_capacity", 2),
        ("ensure_srb", "linear"),
    ]
    assert updates.writes[0] == ("ubuf", 0, b"U" * 8)
    assert updates.writes[1][0] == "ibuf"
    assert len(updates.writes[1][2]) == 2 * ARRAY_INSTANCE_STRIDE


def test_record_array_draw_applies_bbox_resolver():
    resources = _FakeResources()
    updates = _FakeUpdates()
    command_buffer = _FakeCommandBuffer()

    record_array_draw(
        command_buffer,
        resources=resources,
        vertex_buffer="vbo",
        instances=[_inst(1, 2), _inst(3, 4)],
        uniform_bytes=None,
        target=_target(),
        clear_color="clear",
        updates=updates,
        bbox_resolver=lambda index, inst: (float(index), 0.0, 1.0, 1.0),
    )

    blob = updates.writes[0][2]
    assert struct.unpack_from("<4f", blob, _BBOX_OFFSET) == (0.0, 0.0, 1.0, 1.0)
    assert struct.unpack_from("<4f", blob, _BBOX_OFFSET + ARRAY_INSTANCE_STRIDE) == (
        1.0,
        0.0,
        1.0,
        1.0,
    )
    assert updates.writes[0][0] == "ibuf"


def test_record_array_draw_empty_instances_opens_closes_pass_without_draw():
    resources = _FakeResources()
    updates = _FakeUpdates()
    command_buffer = _FakeCommandBuffer()
    pre_begin: list = []
    in_pass: list = []

    record_array_draw(
        command_buffer,
        resources=resources,
        vertex_buffer="vbo",
        instances=[],
        uniform_bytes=None,
        target=_target(),
        clear_color="clear",
        updates=updates,
        pre_begin=lambda: pre_begin.append("pre"),
        in_pass=lambda: in_pass.append("in"),
    )

    assert command_buffer.calls == ["beginPass", "endPass"]
    assert pre_begin == ["pre"]
    assert in_pass == ["in"]
    assert resources.calls == []
    assert updates.writes == []


def test_draw_array_instances_records_documented_sequence():
    resources = _FakeResources()
    command_buffer = _FakeCommandBuffer()

    draw_array_instances(
        command_buffer,
        resources=resources,
        vertex_buffer="vbo",
        instance_count=3,
        sampler_name="nearest",
        viewport_size=(640, 480),
    )

    assert command_buffer.calls == [
        "setGraphicsPipeline",
        "setViewport",
        "setVertexInput",
        "setShaderResources",
        ("draw", 4, 3),
    ]
    assert command_buffer.last_viewport.viewport() == [0.0, 0.0, 640.0, 480.0]
    start, bindings = command_buffer.last_bindings
    assert start == 0
    assert list(bindings) == [("vbo", 0), ("ibuf", 0)]
    assert command_buffer.last_srb == "srb"
    assert resources.calls == [("ensure_srb", "nearest")]


def test_draw_array_instances_defaults_to_resources_sampler():
    resources = _FakeResources()
    command_buffer = _FakeCommandBuffer()

    draw_array_instances(
        command_buffer,
        resources=resources,
        vertex_buffer="vbo",
        instance_count=1,
        viewport_size=(8, 4),
    )

    assert command_buffer.calls[-1] == ("draw", 4, 1)
    assert resources.calls == [("ensure_srb", None)]


def test_record_array_draw_routes_draw_through_draw_array_instances(monkeypatch):
    import engine.gpu.array_draw as array_draw

    resources = _FakeResources()
    updates = _FakeUpdates()
    command_buffer = _FakeCommandBuffer()
    captured: list = []
    real = array_draw.draw_array_instances

    def _spy(cmd, **kwargs):
        captured.append((cmd, kwargs))
        real(cmd, **kwargs)

    monkeypatch.setattr(array_draw, "draw_array_instances", _spy)

    record_array_draw(
        command_buffer,
        resources=resources,
        vertex_buffer="vbo",
        instances=[_inst(1, 2), _inst(3, 4), _inst(5, 6)],
        uniform_bytes=None,
        target=_target(),
        clear_color="clear",
        updates=updates,
    )

    assert len(captured) == 1
    spy_cmd, spy_kwargs = captured[0]
    assert spy_cmd is command_buffer
    assert spy_kwargs == {
        "resources": resources,
        "vertex_buffer": "vbo",
        "instance_count": 3,
        "sampler_name": "linear",
        "viewport_size": (10, 20),
    }
    assert command_buffer.calls == [
        "beginPass",
        "setGraphicsPipeline",
        "setViewport",
        "setVertexInput",
        "setShaderResources",
        ("draw", 4, 3),
        "endPass",
    ]


def test_record_array_draw_accepts_slot_instance_without_sampler_name():
    """Slot instances (the engine slot pass) carry no ``sampler_name``; the
    draw must fall back to the resources' default sampler, not raise.

    Regression for the QL white-canvas crash: ``SlotInstance`` replaced
    ``ArrayInstance`` in the engine view but ``record_array_draw`` still read
    ``instances[0].sampler_name`` unconditionally.
    """
    from engine.gpu.array_draw import SlotInstance, pack_slot_instance

    inst = SlotInstance(
        pan_fit=(0.0, 0.0, 1.0, 1.0),
        zoom=1.0,
        tile_rect=(0.0, 0.0, 0.5, 1.0),
        slot_rect=(0.0, 0.0, 1.0, 1.0),
        content_scale=(1.0, 1.0),
        layer=3,
        bbox=(0.0, 0.0, 1.0, 1.0),
    )
    resources = _FakeResources()
    cmd = _FakeCommandBuffer()
    record_array_draw(
        cmd,
        resources=resources,
        vertex_buffer="vbo",
        instances=[inst],
        uniform_bytes=b"\x00" * 80,
        target=_target(),
        clear_color=None,
        updates=_FakeUpdates(),
        pack_instance=pack_slot_instance,
    )
    assert ("draw", 4, 1) in cmd.calls
    assert ("ensure_srb", None) in resources.calls
