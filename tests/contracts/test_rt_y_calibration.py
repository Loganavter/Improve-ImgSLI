"""Self-calibration of the SAMPLED_RT Y flip (``IMGSLI_RT_ORIENTATION_PROBE``).

Why this exists (task-rt-y-calibration-probe-2026-10-24): the flip in
``engine/gpu/rt_y_orientation.py`` is derived from two documented QRhi
properties and MEASURED on OpenGL/Vulkan/D3D11 -- Metal and D3D12 are only
predicted, and a future Qt could change what the queries mean. Behind
``IMGSLI_RT_ORIENTATION_PROBE=1`` the mip cascade therefore renders a tiny
asymmetric source through its REAL downsample pipeline into its REAL scratch
target, reads it back, and reports the flip the target actually needed via
``record_sampled_rt_orientation``; that observation wins for that RHI only.

Pinned here, with fake RHIs / fake readbacks and no device:

1. agreement records the observation and leaves the correction alone;
2. disagreement flips the correction for THAT rhi only and emits a loud
   ``logger.warning`` (caplog) even with ``IMGSLI_RT_ORIENTATION_TRACE`` off;
3. an unreadable readback (``None``) keeps the derived rule and warns about
   nothing;
4. flag off: a full ``generate_all_dirty_mips`` probes nothing -- no extra
   texture/pass/readback/``rhi.finish()``, no override;
5. flag on: exactly one probe per RHI, so the second cascade call does not
   re-probe (and does not re-render or re-read the calibration source).

The fake-rhi idiom mirrors ``tests/render/test_mip_cascade_y_parity.py`` and
``src/tabs/image_gallery/tests/runtime/test_ql_mip_cascade_not_ready.py``:
module-level Qt constructor names are substituted, so nothing here needs a
window, a QRhi device or a shader compiler.
"""

from __future__ import annotations

import logging
import struct
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QSize

from engine.gpu import rt_y_orientation as rt
from engine.gpu import mip_cascade as mc
from engine.gpu.mip_cascade import MipCascadeGenerator

IDENTITY = (
    1.0, 0.0, 0.0, 0.0,
    0.0, 1.0, 0.0, 0.0,
    0.0, 0.0, 1.0, 0.0,
    0.0, 0.0, 0.0, 1.0,
)
Y_FLIP = (
    1.0, 0.0, 0.0, 0.0,
    0.0, -1.0, 0.0, 0.0,
    0.0, 0.0, 1.0, 0.0,
    0.0, 0.0, 0.0, 1.0,
)


class _Rhi:
    """Fake QRhi exposing the two documented orientation properties."""

    def __init__(
        self,
        y_up_framebuffer: bool,
        y_up_ndc: bool,
        *,
        backend: str = "OpenGL",
    ) -> None:
        self.y_up_framebuffer = y_up_framebuffer
        self.y_up_ndc = y_up_ndc
        self.backend = backend

    def isYUpInFramebuffer(self) -> bool:
        return self.y_up_framebuffer

    def isYUpInNDC(self) -> bool:
        return self.y_up_ndc

    def backendName(self) -> str:
        return self.backend


@pytest.fixture(autouse=True)
def _fresh_orientation_state():
    """Module registries are process-wide (like ``_traced``): isolate tests."""
    rt._observed_flips.clear()
    rt._probe_claimed.clear()
    rt._traced.clear()
    yield
    rt._observed_flips.clear()
    rt._probe_claimed.clear()
    rt._traced.clear()


def _warnings(caplog) -> list[logging.LogRecord]:
    return [
        record
        for record in caplog.records
        if record.levelno == logging.WARNING and "[rt-y]" in record.getMessage()
    ]


# -- 1. agreement -----------------------------------------------------------


def test_agreement_records_the_override_and_keeps_the_correction():
    opengl = _Rhi(True, True)  # derived: flip
    assert rt.sampled_rt_correction(opengl) == Y_FLIP

    rt.record_sampled_rt_orientation(opengl, observed_flip=True)

    assert rt.sampled_rt_correction(opengl) == Y_FLIP, (
        "an agreeing observation must not change the correction"
    )
    # The observation is recorded, not merely re-derived: moving the fake's
    # queries must not move the answer any more.
    opengl.y_up_framebuffer = False
    opengl.y_up_ndc = True
    assert rt.sampled_rt_needs_y_flip(opengl) is True, (
        "the recorded flip must win over the (now D3D-like) derived rule"
    )

    d3d = _Rhi(False, True, backend="D3D11")
    assert rt.sampled_rt_correction(d3d) == IDENTITY
    rt.record_sampled_rt_orientation(d3d, observed_flip=False)
    assert rt.sampled_rt_correction(d3d) == IDENTITY


# -- 2. disagreement --------------------------------------------------------


def test_disagreement_flips_that_rhi_only_and_warns(caplog):
    opengl = _Rhi(True, True, backend="OpenGL")
    vulkan = _Rhi(False, False, backend="Vulkan")
    assert rt.sampled_rt_needs_y_flip(opengl) is True
    assert rt.sampled_rt_needs_y_flip(vulkan) is True

    with caplog.at_level(logging.WARNING):
        rt.record_sampled_rt_orientation(opengl, observed_flip=False)

    assert rt.sampled_rt_needs_y_flip(opengl) is False
    assert rt.sampled_rt_correction(opengl) == IDENTITY, (
        "a disagreeing observation must flip the correction for that rhi"
    )
    assert rt.sampled_rt_needs_y_flip(vulkan) is True, (
        "an override is per-rhi-session, never a process-wide flip"
    )
    assert rt.sampled_rt_correction(vulkan) == Y_FLIP

    warnings = _warnings(caplog)
    assert len(warnings) == 1, (
        "a disagreement must be logged LOUDLY (logger.warning), always -- "
        f"not gated on IMGSLI_RT_ORIENTATION_TRACE; got {caplog.records!r}"
    )
    message = warnings[0].getMessage()
    for fragment in (
        "backend=OpenGL",
        "predicted_flip=True",
        "observed_flip=False",
        "rt_y_orientation.py",
    ):
        assert fragment in message, f"disagreement log lost {fragment!r}: {message}"


# -- 3. unreadable readback -------------------------------------------------


def test_unreadable_readback_keeps_the_derived_rule_without_warning(caplog):
    d3d = _Rhi(False, True, backend="D3D11")
    assert rt.sampled_rt_needs_y_flip(d3d) is False

    with caplog.at_level(logging.DEBUG):
        rt.record_sampled_rt_orientation(d3d, observed_flip=None)

    assert rt.sampled_rt_needs_y_flip(d3d) is False
    assert not _warnings(caplog), (
        "an unreadable probe must not pretend it measured a disagreement"
    )
    infos = [
        record
        for record in caplog.records
        if record.levelno == logging.INFO and "[rt-y]" in record.getMessage()
    ]
    assert len(infos) == 1, "the probe should log at info once that it was unreadable"

    # No override was recorded: the derived rule is still live.
    d3d.y_up_framebuffer = False
    d3d.y_up_ndc = False
    assert rt.sampled_rt_needs_y_flip(d3d) is True


# -- pure readback parser ---------------------------------------------------


def _rgba_rows(top: int, bottom: int) -> bytes:
    row = bytes((top, top, top, 255)) * 2
    return row + bytes((bottom, bottom, bottom, 255)) * 2


def test_readback_parser_reads_rows_and_rejects_noise():
    assert mc.probe_upright_from_rgba8(_rgba_rows(255, 0), 2, 2) is True
    assert mc.probe_upright_from_rgba8(_rgba_rows(0, 255), 2, 2) is False
    assert mc.probe_upright_from_rgba8(b"", 2, 2) is None
    assert mc.probe_upright_from_rgba8(_rgba_rows(0, 0), 2, 2) is None, (
        "a dropped draw (uniform clear colour) must read as unreadable, never "
        "as a coin-flip orientation"
    )
    assert mc.probe_upright_from_rgba8(b"\x00" * 8, 2, 2) is None, (
        "a short readback must not be sliced into a guess"
    )


# -- fake device for the full cascade path ----------------------------------


class _FakeResource:
    def __init__(self, *args, **kwargs) -> None:
        self.destroyed = False

    def setName(self, _name) -> None:
        pass

    def create(self) -> bool:
        return True

    def destroy(self) -> None:
        self.destroyed = True


class _FakePipeline(_FakeResource):
    def setShaderStages(self, _stages) -> None:
        pass

    def setTopology(self, _topology) -> None:
        pass

    def setSampleCount(self, _count) -> None:
        pass

    def setRenderPassDescriptor(self, _descriptor) -> None:
        pass

    def setVertexInputLayout(self, _layout) -> None:
        pass

    def setShaderResourceBindings(self, _srb) -> None:
        pass


class _FakeSrb(_FakeResource):
    def setBindings(self, _bindings) -> None:
        pass


class _FakeTexture(_FakeResource):
    pass


class _FakeTarget(_FakeResource):
    def newCompatibleRenderPassDescriptor(self):
        return _FakeResource()

    def setRenderPassDescriptor(self, _descriptor) -> None:
        pass

    def sampleCount(self) -> int:
        return 1


class _FakeBatch:
    def __init__(self, rhi) -> None:
        self.rhi = rhi
        self.dynamic_writes: list[tuple] = []

    def updateDynamicBuffer(self, buffer, offset, data) -> None:
        self.dynamic_writes.append((buffer, offset, bytes(data)))

    def uploadStaticBuffer(self, _buffer, _data) -> None:
        pass

    def uploadTexture(self, _texture, _entry) -> None:
        self.rhi.upload_calls += 1

    def copyTexture(self, *_args, **_kwargs) -> None:
        pass

    def readBackTexture(self, _description, result) -> None:
        self.rhi.readback_calls += 1
        result.data = self.rhi.readback_data
        result.pixelSize = QSize(2, 2)


class _FakeCommandBuffer:
    def __init__(self) -> None:
        self.passes = 0
        self.draws = 0
        self.batches: list[_FakeBatch] = []

    def resourceUpdate(self, batch) -> None:
        self.batches.append(batch)

    def beginPass(self, *_args, **_kwargs) -> None:
        self.passes += 1

    def endPass(self) -> None:
        pass

    def setGraphicsPipeline(self, _pipeline) -> None:
        pass

    def setViewport(self, _viewport) -> None:
        pass

    def setVertexInput(self, _binding, _inputs) -> None:
        pass

    def setShaderResources(self, _srb, *args) -> None:
        pass

    def draw(self, _count) -> None:
        self.draws += 1


class _FakeRhi:
    """Enough QRhi for the real cascade to record its passes on fakes."""

    def __init__(
        self,
        y_up_framebuffer: bool,
        y_up_ndc: bool,
        *,
        backend: str = "OpenGL",
        readback: bytes | None = None,
    ) -> None:
        self.y_up_framebuffer = y_up_framebuffer
        self.y_up_ndc = y_up_ndc
        self.backend = backend
        self.readback_data = (
            _rgba_rows(255, 0) if readback is None else readback
        )
        self.finish_calls = 0
        self.readback_calls = 0
        self.upload_calls = 0
        self.texture_array_calls = 0

    def isYUpInFramebuffer(self) -> bool:
        return self.y_up_framebuffer

    def isYUpInNDC(self) -> bool:
        return self.y_up_ndc

    def backendName(self) -> str:
        return self.backend

    def ubufAligned(self, value: int) -> int:
        return int(value)

    def newBuffer(self, *_args, **_kwargs) -> _FakeResource:
        return _FakeResource()

    def newGraphicsPipeline(self) -> _FakePipeline:
        return _FakePipeline()

    def newShaderResourceBindings(self) -> _FakeSrb:
        return _FakeSrb()

    def newTexture(self, *_args, **_kwargs) -> _FakeTexture:
        return _FakeTexture()

    def newTextureArray(self, *_args, **_kwargs) -> _FakeTexture:
        self.texture_array_calls += 1
        return _FakeTexture()

    def newTextureRenderTarget(self, _description=None) -> _FakeTarget:
        return _FakeTarget()

    def nextResourceUpdateBatch(self) -> _FakeBatch:
        return _FakeBatch(self)

    def finish(self) -> None:
        self.finish_calls += 1


def _patch_qt_objects(monkeypatch) -> None:
    monkeypatch.setattr(
        mc,
        "QRhiColorAttachment",
        lambda _texture: SimpleNamespace(
            setLayer=lambda _index: None, setLevel=lambda _index: None
        ),
    )
    monkeypatch.setattr(mc, "QRhiTextureRenderTargetDescription", lambda att: att)
    class _FakeShaderStage:
        Type = SimpleNamespace(Vertex=1, Fragment=2)

        def __init__(self, *_args) -> None:
            pass

    monkeypatch.setattr(mc, "QRhiShaderStage", _FakeShaderStage)
    monkeypatch.setattr(mc, "_load_mip_downsample_shader", lambda _name: object())
    monkeypatch.setattr(
        mc,
        "QRhiShaderResourceBinding",
        SimpleNamespace(
            StageFlag=SimpleNamespace(FragmentStage=1, VertexStage=2),
            uniformBufferWithDynamicOffset=lambda *args: ("ubo", args),
            sampledTexture=lambda *args: ("sampled", args),
            uniformBuffer=lambda *args: ("ubuf", args),
        ),
    )
    monkeypatch.setattr(
        mc,
        "QRhiReadbackResult",
        lambda: SimpleNamespace(data=b"", pixelSize=QSize(0, 0)),
    )
    monkeypatch.setattr(mc, "QRhiReadbackDescription", lambda *_args: object())
    monkeypatch.setattr(mc, "tile_dump_enabled", lambda: False)


def _generator(rhi, *, layer_px: int = 16) -> MipCascadeGenerator:
    return MipCascadeGenerator(
        rhi_getter=lambda: rhi,
        tile_arrays=[_FakeTexture()],
        ensure_tile_array=lambda _index: None,
        sampler_getter=lambda: object(),
        layer_px=layer_px,
        name_prefix="test",
    )


def _run_plan(rhi, *, layer_px: int = 16):
    generator = _generator(rhi, layer_px=layer_px)
    command_buffer = _FakeCommandBuffer()
    deferred = generator.generate_all_dirty_mips(
        command_buffer, _FakeResource(), {0: {0}}, None
    )
    return generator, command_buffer, deferred


# -- 4. flag off: no probe at all -------------------------------------------


def test_flag_off_probes_nothing_and_records_no_override(monkeypatch):
    _patch_qt_objects(monkeypatch)
    monkeypatch.setattr(rt, "_PROBE_ENABLED", False)
    rhi = _FakeRhi(True, True, backend="OpenGL")

    generator, command_buffer, deferred = _run_plan(rhi)

    assert deferred == {}
    assert rhi.texture_array_calls == 0, "flag off must not create the probe source"
    assert rhi.upload_calls == 0, "flag off must not upload the probe pattern"
    assert rhi.readback_calls == 0, "flag off must not read anything back"
    assert rhi.finish_calls == 0, "flag off must not sync the GPU"
    assert rt._observed_flips == {}, "flag off must record no override"
    assert rt._probe_claimed == set(), "flag off must not even claim a probe"
    assert generator._orientation_probe_source is None
    assert generator._orientation_probe_srb is None
    # The real cascade still ran one pass per generated level.
    assert command_buffer.draws == 4


def test_flag_off_uploads_the_same_plan_as_before_the_probe(monkeypatch):
    """The default path must be byte-identical: one correction write, real slots.

    Pre-probe, ``generate_all_dirty_mips`` wrote the derived matrix once and
    one uniform slot per ``(layer, level)`` draw. With the flag off that is
    still the whole command stream -- no probe slot, no probe batch.
    """
    _patch_qt_objects(monkeypatch)
    monkeypatch.setattr(rt, "_PROBE_ENABLED", False)
    rhi = _FakeRhi(True, True, backend="OpenGL")

    _generator_, command_buffer, _deferred = _run_plan(rhi)

    writes = [
        (offset, payload)
        for batch in command_buffer.batches
        for (_buffer, offset, payload) in batch.dynamic_writes
    ]
    corr_writes = [payload for _offset, payload in writes if len(payload) == 64]
    assert corr_writes == [struct.pack("<16f", *Y_FLIP)], (
        "flag off must write exactly the derived correction, once"
    )
    slots = [payload for _offset, payload in writes if len(payload) == 16]
    assert slots == [
        struct.pack("<iiii", 0, level - 1, 0, 0) for level in range(1, 5)
    ], "flag off must write one uniform slot per real level, nothing else"


# -- 5. flag on: exactly one probe per rhi ----------------------------------


def test_flag_on_probes_once_per_rhi_and_records_agreement(monkeypatch):
    _patch_qt_objects(monkeypatch)
    monkeypatch.setattr(rt, "_PROBE_ENABLED", True)
    rhi = _FakeRhi(True, True, backend="OpenGL")

    generator, first_buffer, _deferred = _run_plan(rhi)
    assert rhi.texture_array_calls == 1, "the first cascade call renders one probe"
    assert rhi.upload_calls == 1, "the probe uploads its 2x2 pattern once"
    assert rhi.readback_calls == 1
    assert rhi.finish_calls == 1
    assert rt.sampled_rt_needs_y_flip(rhi) is True
    assert id(rhi) in rt._observed_flips

    second_buffer = _FakeCommandBuffer()
    generator.generate_all_dirty_mips(second_buffer, _FakeResource(), {0: {1}}, None)

    assert rhi.texture_array_calls == 1, "the second call must not re-probe"
    assert rhi.readback_calls == 1, "the second call must not re-read the target"
    assert rhi.finish_calls == 1, "no extra GPU sync once the probe is claimed"
    # Real level work still happened both times.
    assert first_buffer.draws == 5, "probe pass + 4 real levels on the first call"
    assert second_buffer.draws == 4, "only the real levels afterwards"


def test_flag_on_disagreement_overrides_the_correction_for_that_rhi(monkeypatch, caplog):
    _patch_qt_objects(monkeypatch)
    monkeypatch.setattr(rt, "_PROBE_ENABLED", True)
    # OpenGL-like predicates (derived flip) but a target that read back flipped.
    rhi = _FakeRhi(True, True, backend="OpenGL", readback=_rgba_rows(0, 255))

    with caplog.at_level(logging.WARNING):
        _generator_, buffer, _deferred = _run_plan(rhi)

    assert rt.sampled_rt_needs_y_flip(rhi) is False
    assert rt.sampled_rt_correction(rhi) == IDENTITY
    corr_writes = [
        payload
        for batch in buffer.batches
        for (_buffer, _offset, payload) in batch.dynamic_writes
        if len(payload) == 64
    ]
    assert corr_writes == [
        struct.pack("<16f", *Y_FLIP),
        struct.pack("<16f", *IDENTITY),
    ], (
        "the probe pass uses the predicted matrix, then the real levels in the "
        "same frame must already use the observed one"
    )
    assert len(_warnings(caplog)) == 1
    assert "observed_flip=False" in _warnings(caplog)[0].getMessage()


def test_flag_on_unreadable_probe_keeps_the_rule_and_does_not_raise(monkeypatch, caplog):
    _patch_qt_objects(monkeypatch)
    monkeypatch.setattr(rt, "_PROBE_ENABLED", True)
    rhi = _FakeRhi(True, True, backend="OpenGL", readback=b"")

    with caplog.at_level(logging.INFO):
        _generator_, buffer, deferred = _run_plan(rhi)

    assert deferred == {}
    assert rt.sampled_rt_needs_y_flip(rhi) is True, (
        "an unreadable probe keeps the derived rule"
    )
    assert not _warnings(caplog)
    assert buffer.draws == 5, "the probe pass still ran once, then the real levels"
    assert rhi.readback_calls == 1
