"""Half-init latch: a raising feature pass must not latch the IC renderer.

Falsification story (docs/dev/TESTING.md § Rules for writing new tests):
before the fix ``initialize()`` assigned ``self.feature_passes`` *ahead* of
the init loop, so one raising pass left a non-empty, half-initialized list.
The same-rhi early return then keyed off that list (``if new_rhi is self.rhi
and self.feature_passes: return``), i.e. the renderer treated the broken
attempt as complete and never retried -- every later frame drew with
uninitialized passes. Both tests below drive the real
``RhiCanvasRenderer.initialize()`` against fakes (no GPU, no live render) and
fail on that code: the latch test because ``feature_passes`` is non-empty
after the raise and the retry early-returns, the success-path control because
a "publish nothing ever" implementation cannot set the flags asserted there.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from engine.gpu.glass_panel import GlassPanelRenderer
from tabs.image_compare.canvas.rhi_renderer import renderer as renderer_mod
from tabs.image_compare.canvas.rhi_renderer.renderer import RhiCanvasRenderer
from tabs.image_compare.canvas.rhi_renderer.resources import RhiResources


class _RegistryStub:
    """``registry()`` stand-in: hands out prototype instances, counts calls."""

    def __init__(self, prototypes: list) -> None:
        self._prototypes = list(prototypes)
        self.calls = 0

    def get_render_passes(self) -> list:
        self.calls += 1
        return list(self._prototypes)


class _GoodPass:
    """Feature-pass fake; ``on_initialize`` collects the instances the
    renderer actually built (the probe is set per test, so building the
    prototype instance itself records nothing)."""

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


def _patch_gpu_boundary(monkeypatch, registry_stub):
    """Stub everything ``initialize()`` touches outside the pass loop."""
    monkeypatch.setattr(RhiResources, "initialize", lambda self, *a, **k: None)
    monkeypatch.setattr(
        RhiResources, "restore_texture_uploads", lambda self, *a, **k: None
    )
    monkeypatch.setattr(GlassPanelRenderer, "initialize", lambda self, rhi: None)
    monkeypatch.setattr(renderer_mod, "query_max_texture_size", lambda rhi: 16384)
    monkeypatch.setattr(
        "tabs.image_compare.canvas.registry.registry", lambda: registry_stub
    )


def _fake_widget(rhi):
    return SimpleNamespace(
        rhi=lambda: rhi,
        renderTarget=lambda: SimpleNamespace(pixelSize=lambda: (100, 80)),
        width=lambda: 100,
        height=lambda: 80,
        api=lambda: SimpleNamespace(name="fake"),
    )


def _fake_rhi():
    return SimpleNamespace(resourceLimit=lambda _limit: 16384)


def test_raising_pass_publishes_nothing_and_retries_on_same_rhi(monkeypatch):
    good = []
    raising = []
    _GoodPass.on_initialize = good
    _RaisingPass.on_initialize = raising
    registry_stub = _RegistryStub([_GoodPass(), _RaisingPass()])
    _patch_gpu_boundary(monkeypatch, registry_stub)
    renderer = RhiCanvasRenderer()
    widget = _fake_widget(_fake_rhi())

    with pytest.raises(RuntimeError, match="pass init exploded"):
        renderer.initialize(widget, SimpleNamespace(resources=None))

    # Nothing published: a half-initialized set must never reach render().
    assert renderer.feature_passes == []
    assert renderer.initialized is False
    # The one pass whose initialize() returned is released exactly once; the
    # raising pass is never released (it may own no GPU objects at all).
    assert len(good) == 1 and len(raising) == 1
    assert good[0].initialized is False
    assert good[0].release_calls == 1
    assert getattr(raising[0], "release_calls", 0) == 0

    # Same rhi, second call: the guard must key off completed init, so this
    # is a retry (registry consulted again, fresh passes built), not a no-op.
    with pytest.raises(RuntimeError, match="pass init exploded"):
        renderer.initialize(widget, SimpleNamespace(resources=None))

    assert registry_stub.calls == 2
    assert len(good) == 2 and len(raising) == 2
    assert good[1] is not good[0]
    assert good[1].release_calls == 1


def test_successful_init_publishes_initialized_passes_and_keeps_early_return(monkeypatch):
    """Non-vacuity control: publishing nothing ever cannot pass this."""
    good = []
    _GoodPass.on_initialize = good
    registry_stub = _RegistryStub([_GoodPass(), _GoodPass()])
    _patch_gpu_boundary(monkeypatch, registry_stub)
    renderer = RhiCanvasRenderer()
    widget = _fake_widget(_fake_rhi())

    renderer.initialize(widget, SimpleNamespace(resources=None))

    assert renderer.initialized is True
    assert renderer.feature_passes == good
    assert len(good) == 2
    assert all(pass_.initialized is True for pass_ in good)

    # The resize fast path still works: same rhi + completed init returns
    # without rebuilding (no extra registry consultation, no new instances).
    renderer.initialize(widget, SimpleNamespace(resources=None))

    assert registry_stub.calls == 1
    assert len(good) == 2
    assert renderer.feature_passes == good
