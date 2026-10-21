"""GPU-generation invalidation: a recreated RHI must not inherit stale state.

Dogma (plan-canvas-hardening-2026-10-21, V10 family): every piece of state that
describes *the GPU objects of one RHI generation* dies with that generation. A
renderer that keeps "this tile/texture is already uploaded" bookkeeping across
``release()`` will take the "no upload needed" path against freshly created,
empty textures and show a blank canvas -- the failure multi_compare documents
for its slot bookkeeping.

image_compare gets this by construction: ``release()`` ends with
``self.__init__()``, which rebuilds ``RhiResources``/``TileTextureService`` and
clears ``_last_good_texture_keys``/``_last_good_diff_key``, and
``initialize()`` re-runs ``restore_texture_uploads`` (which re-queues every
cached image from the host QImage cache). These tests PIN that invariant so a
future refactor cannot silently drop it; the last two also prove the re-upload
path is entered after a release, for a new RHI identity and for the same one.
"""

from __future__ import annotations

from types import SimpleNamespace

from tabs.image_compare.canvas.rhi_renderer.renderer import RhiCanvasRenderer
from tabs.image_compare.canvas.rhi_renderer.resources import RhiResources

from .test_rhi_feature_pass_latch import (
    _GoodPass,
    _RegistryStub,
    _fake_widget,
    _patch_gpu_boundary,
)


def test_release_drops_generation_scoped_gpu_state():
    """Everything bound to the old RHI generation is replaced or cleared."""
    renderer = RhiCanvasRenderer()
    old_resources = renderer.resources
    old_tile_service = renderer.tile_service
    old_glass_panel = renderer.glass_panel_renderer
    renderer._last_good_texture_keys = ("stored_0", "stored_1")
    renderer._last_good_diff_key = "diff"
    renderer.feature_passes = [_GoodPass()]
    renderer.initialized = True

    renderer.release()

    assert renderer.resources is not old_resources, "RhiResources survived release()"
    assert renderer.tile_service is not old_tile_service, "tile service survived release()"
    assert renderer.glass_panel_renderer is not old_glass_panel, "glass panel survived release()"
    assert renderer._last_good_texture_keys is None, "fallback LOD keys survived release()"
    assert renderer._last_good_diff_key is None, "diff fallback key survived release()"
    assert renderer.feature_passes == [], "passes survived release()"
    assert renderer.initialized is False, "the completed-init latch survived release()"


def test_initialize_after_release_restores_uploads_for_a_new_rhi(monkeypatch):
    """A new RHI identity re-enters the upload-restore path (no stale skip)."""
    restored: list = []
    _patch_gpu_boundary(monkeypatch, _RegistryStub([_GoodPass()]))
    monkeypatch.setattr(
        RhiResources,
        "restore_texture_uploads",
        staticmethod(lambda widget: restored.append(widget)),
    )

    renderer = RhiCanvasRenderer()
    widget_a = _fake_widget(object())
    widget_b = _fake_widget(object())
    renderer.initialize(widget_a, SimpleNamespace())
    renderer.release()
    renderer.initialize(widget_b, SimpleNamespace())

    assert restored == [widget_a, widget_b], (
        "restore_texture_uploads must run for every initialize(); "
        f"got {len(restored)} call(s)"
    )
    assert renderer.initialized is True


def test_same_rhi_after_release_still_restores_uploads(monkeypatch):
    """The same-rhi fast path must not survive a release()."""
    restored: list = []
    _patch_gpu_boundary(monkeypatch, _RegistryStub([_GoodPass()]))
    monkeypatch.setattr(
        RhiResources,
        "restore_texture_uploads",
        staticmethod(lambda widget: restored.append(widget)),
    )

    renderer = RhiCanvasRenderer()
    rhi = object()
    widget = _fake_widget(rhi)
    renderer.initialize(widget, SimpleNamespace())
    renderer.release()
    renderer.initialize(_fake_widget(rhi), SimpleNamespace())

    assert len(restored) == 2, (
        "after release() the same RHI must re-initialize, not early-return "
        f"(restore calls: {len(restored)})"
    )
