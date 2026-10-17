"""Mip cascade: a not-creatable probe target is a *retryable* "not ready".

Live evidence (2026-10-17, private Xvfb, OpenGL on LLVMpipe): the first one
or two tiled frames after a store swap reach
``MipCascadeGenerator._ensure_downsample_pipeline`` and get
``probe_target.create() is False``; a later attempt in the same session
succeeds and the takeover lands. Pinned here:

- the raise is the dedicated ``MipCascadeNotReady`` -- a caller (the QL
  canvas) can retry it quietly instead of reporting a broken frame -- and
  it carries the attempt count plus the probe's identity (array, level,
  backend); a bare ``False`` has no facts to diagnose with;
- a rejected attempt consumes **both** half-created resources (the render
  target and its render pass descriptor): dropping the Python wrappers
  leaks the driver objects until the RHI itself is destroyed, and a
  rejected attempt repeats on every store swap;
- the failure is not memoized: the next frame's call tries again.

No GPU: ``QRhiColorAttachment`` / ``QRhiTextureRenderTargetDescription``
are module-level names in ``mip_cascade`` and are substituted here, with a
fake RHI behind them; that is the whole surface the failing path touches.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from PySide6.QtCore import QSize


class _RpDesc:
    def __init__(self) -> None:
        self.destroyed = False

    def destroy(self) -> None:
        self.destroyed = True


class _ProbeTarget:
    def __init__(self, *, created: bool) -> None:
        self._created = created
        self.destroyed = False
        self.rp = _RpDesc()

    def newCompatibleRenderPassDescriptor(self):
        return self.rp

    def setRenderPassDescriptor(self, _rp) -> None:
        pass

    def create(self) -> bool:
        return self._created

    def destroy(self) -> None:
        self.destroyed = True


class _FakeRhi:
    def __init__(self, *, created: bool) -> None:
        self._created = created
        self.calls = 0
        self.target: _ProbeTarget | None = None

    def newTextureRenderTarget(self, _desc) -> _ProbeTarget:
        self.calls += 1
        self.target = _ProbeTarget(created=self._created)
        return self.target

    def backendName(self) -> str:
        return "OpenGL"


def _fake_array_texture():
    return SimpleNamespace(
        pixelSize=lambda: QSize(1024, 1024),
        format=lambda: "RGBA8",
    )


def _generator(monkeypatch, rhi, texture):
    from engine.gpu import mip_cascade as mc

    monkeypatch.setattr(
        mc,
        "QRhiColorAttachment",
        lambda _tex: SimpleNamespace(setLayer=lambda _i: None, setLevel=lambda _i: None),
    )
    monkeypatch.setattr(mc, "QRhiTextureRenderTargetDescription", lambda att: att)
    return mc, mc.MipCascadeGenerator(
        rhi_getter=lambda: rhi,
        tile_arrays=[texture],
        ensure_tile_array=lambda _index: None,
        sampler_getter=lambda: None,
        layer_px=1024,
        name_prefix="ql",
    )


def test_probe_create_failure_is_not_ready_and_releases_both(monkeypatch) -> None:
    rhi = _FakeRhi(created=False)
    mc, gen = _generator(monkeypatch, rhi, _fake_array_texture())

    with pytest.raises(mc.MipCascadeNotReady) as err:
        gen._ensure_downsample_pipeline()

    assert err.value.attempt == 1
    message = str(err.value)
    assert "probe mip render target" in message
    assert "attempt 1" in message
    assert "backend=OpenGL" in message, "the backend is part of the diagnosis"
    assert "attachment=layer0/level1" in message
    assert "layer_px=1024" in message

    target = rhi.target
    assert target is not None
    assert target.destroyed, "the failed probe target must be released, not dropped"
    assert target.rp.destroyed, "…and so must its render pass descriptor"
    assert gen._downsample_pipeline is None, "a rejected attempt installs no pipeline"


def test_rejected_probe_attempt_is_retried_not_memoized(monkeypatch) -> None:
    rhi = _FakeRhi(created=False)
    mc, gen = _generator(monkeypatch, rhi, _fake_array_texture())

    for _ in range(2):
        with pytest.raises(mc.MipCascadeNotReady):
            gen._ensure_downsample_pipeline()

    assert gen._probe_create_failures == 2, "the attempt counter advances per try"
    assert rhi.calls == 2, "the next frame must try again, not skip the pipeline"
