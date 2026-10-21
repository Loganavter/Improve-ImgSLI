"""MC renderer lifetime: half-init latch + one base pass per renderer.

Two defects, both proven by the tests below against fakes (no GPU, no live
render; the success path's QRhi calls are stubbed, the pass lifetime is real):

1. Half-init latch (mirrors image_compare's identical guard).
   ``initialize()`` assigned ``self.feature_passes`` *ahead* of the init
   loop, so one raising pass left a non-empty, half-initialized list and the
   same-rhi early return (``if new_rhi is self.rhi and self.feature_passes``)
   treated that attempt as complete -- the renderer never retried and every
   later frame drew with uninitialized passes.

2. Shared base pass. ``_manifest_base_images_pass()`` returned the
   module-level ``RENDER_PASSES`` instance, so the live canvas renderer and
   the export renderer shared one ``BaseImagesPass`` -- one set of tile
   arrays and slot bookkeeping, and ``release()`` on one cleared both.

Falsification story (docs/dev/TESTING.md § Rules for writing new tests):
each test fails on the pre-fix source (non-empty latch / early return, or
``r1.image_pass is r2.image_pass``) and passes only when publication is
deferred to full success and the pass is instantiated per renderer.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from engine.gpu.glass_panel import GlassPanelRenderer
from tabs.multi_compare.scene import renderer as renderer_mod
from tabs.multi_compare.scene.passes import RENDER_PASSES
from tabs.multi_compare.scene.renderer import MultiCompareRhiRenderer


class _RegistryStub:
    def __init__(self, prototypes: list) -> None:
        self._prototypes = list(prototypes)
        self.calls = 0

    def get_render_passes(self) -> list:
        self.calls += 1
        return list(self._prototypes)


class _GoodPass:
    """Feature-pass fake; ``on_initialize`` collects built instances."""

    on_initialize: list = []

    def initialize(self, rhi, target) -> None:
        self.initialized = True
        type(self).on_initialize.append(self)

    def release(self) -> None:
        self.release_calls = getattr(self, "release_calls", 0) + 1
        self.initialized = False


class _RaisingPass:
    on_initialize: list = []

    def initialize(self, rhi, target) -> None:
        type(self).on_initialize.append(self)
        raise RuntimeError("pass init exploded")

    def release(self) -> None:  # pragma: no cover - must never be called
        self.release_calls = getattr(self, "release_calls", 0) + 1


def _fake_rhi():
    sampler = SimpleNamespace(create=lambda: True, destroy=lambda: None)
    texture = SimpleNamespace(create=lambda: True, destroy=lambda: None)
    batch = SimpleNamespace(uploadTexture=lambda *a, **k: None)
    return SimpleNamespace(
        resourceLimit=lambda _limit: 16384,
        ubufAligned=lambda size: ((size + 255) // 256) * 256,
        newSampler=lambda *a, **k: sampler,
        newTexture=lambda *a, **k: texture,
        nextResourceUpdateBatch=lambda: batch,
    )


def _fake_host(rhi):
    return SimpleNamespace(
        rhi=lambda: rhi,
        renderTarget=lambda: SimpleNamespace(pixelSize=lambda: (100, 80)),
        _sync_textures=lambda: None,
    )


def _patch_gpu_boundary(monkeypatch, registry_stub):
    monkeypatch.setattr(GlassPanelRenderer, "initialize", lambda self, rhi: None)
    monkeypatch.setattr(renderer_mod, "query_max_texture_size", lambda rhi: 16384)
    monkeypatch.setattr(renderer_mod, "registry", lambda: registry_stub)


def _fake_command_buffer():
    return SimpleNamespace(resourceUpdate=lambda *a, **k: None)


def test_raising_pass_publishes_nothing_and_retries_on_same_rhi(monkeypatch):
    good: list = []
    raising: list = []
    _GoodPass.on_initialize = good
    _RaisingPass.on_initialize = raising
    registry_stub = _RegistryStub([_GoodPass(), _RaisingPass()])
    _patch_gpu_boundary(monkeypatch, registry_stub)
    renderer = MultiCompareRhiRenderer(_fake_host(_fake_rhi()))
    command_buffer = _fake_command_buffer()

    with pytest.raises(RuntimeError, match="pass init exploded"):
        renderer.initialize(command_buffer)

    assert renderer.feature_passes == []
    assert renderer.initialized is False
    assert len(good) == 1 and len(raising) == 1
    assert good[0].initialized is False
    assert good[0].release_calls == 1
    assert getattr(raising[0], "release_calls", 0) == 0

    # Same rhi, second call: retried (registry consulted again) instead of
    # short-circuiting on the stale half-initialized list.
    with pytest.raises(RuntimeError, match="pass init exploded"):
        renderer.initialize(command_buffer)

    assert registry_stub.calls == 2
    assert len(good) == 2 and len(raising) == 2
    assert good[1] is not good[0]
    assert good[1].release_calls == 1


def test_successful_init_publishes_initialized_passes_and_keeps_early_return(monkeypatch):
    """Non-vacuity control: publishing nothing ever cannot pass this."""
    good: list = []
    _GoodPass.on_initialize = good
    registry_stub = _RegistryStub([_GoodPass(), _GoodPass()])
    _patch_gpu_boundary(monkeypatch, registry_stub)
    renderer = MultiCompareRhiRenderer(_fake_host(_fake_rhi()))
    command_buffer = _fake_command_buffer()

    renderer.initialize(command_buffer)

    assert renderer.initialized is True
    assert renderer.feature_passes == good
    assert len(good) == 2
    assert all(pass_.initialized is True for pass_ in good)

    # Resize fast path preserved: same rhi + completed init does not rebuild.
    renderer.initialize(command_buffer)

    assert registry_stub.calls == 1
    assert len(good) == 2


def test_each_renderer_owns_its_own_base_images_pass():
    """Two renderers built from the same class must not share the base pass.

    Before the fix both took the module-level ``RENDER_PASSES`` instance, so
    releasing one renderer's pass cleared the other's slot bookkeeping
    mid-flight (live canvas and export renderer in the same process).
    """
    r1 = MultiCompareRhiRenderer(SimpleNamespace())
    r2 = MultiCompareRhiRenderer(SimpleNamespace())

    assert type(r1.image_pass) is type(r2.image_pass)
    assert r1.image_pass is not r2.image_pass
    # The manifest instance itself is never handed to a renderer.
    assert all(p is not r1.image_pass for p in RENDER_PASSES)

    rhi = _fake_rhi()
    target = SimpleNamespace(pixelSize=lambda: (100, 80))
    r1.image_pass.initialize(rhi, target)
    r2.image_pass.initialize(rhi, target)

    sentinel1, sentinel2 = object(), object()
    r1.image_pass.slot_pixel_sources[1] = sentinel1
    r2.image_pass.slot_pixel_sources[2] = sentinel2
    r2.image_pass.pending_uploads.append((2, sentinel2))

    r1.image_pass.release()

    assert r1.image_pass.slot_pixel_sources == {}
    assert r2.image_pass.slot_pixel_sources == {2: sentinel2}
    assert r2.image_pass.pending_uploads == [(2, sentinel2)]
