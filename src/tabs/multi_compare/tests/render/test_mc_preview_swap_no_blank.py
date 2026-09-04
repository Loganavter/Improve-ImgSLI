"""MC preview->full swap keeps the old tier visible (A4, no blank window).

Pins ``BaseImagesPass._upload_slot``'s A4 hardening: a same-``sid`` source
swap must never destroy the only visible content before the replacement's
own tiles land.

- 1x1-preview -> multi-full rekeys the preview under the fallback key,
  backfills its single tile into the array (plain textures are not
  drawable on the array path), keeps the stale plain texture alive, and
  defers its release until the new key promotes.
- 1x1 -> 1x1 stays a same-frame plain overwrite (no blank either way).
- True duplicate uploads (same object) stay a no-op and create no
  fallback bookkeeping.
"""
from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtGui import QImage

from shared.image_processing.tiled_pixel_store import TiledPixelStore
from shared.rendering.tile_texture_service import TileTextureService
from tabs.multi_compare.scene.passes.base_images import BaseImagesPass


class _FakeTexture:
    def __init__(self, *args):
        self.args = args

    def create(self):
        return True

    def destroy(self):
        pass


class _FakeRhi:
    def newTexture(self, *args):
        return _FakeTexture(*args)


class _FakeUpdates:
    def uploadTexture(self, *args):
        pass


class _StubArrayResources:
    """Captures backfill uploads without any GPU work."""

    def __init__(self, tile_service):
        self.tile_service = tile_service
        self.uploads: list[tuple[object, tuple[int, int]]] = []

    def upload_tile_to_array(
        self, tile_service, key, index, image, updates, dirty_layers=None
    ):
        self.uploads.append((key, index))
        tile_service.mark_resident(key, index, image.width() * image.height() * 4)
        if dirty_layers is not None:
            dirty_layers.setdefault(0, set()).add(0)
        return (key, *index)


def _setup(*, max_tile_extent=256):
    rp = BaseImagesPass()
    host = SimpleNamespace(update=lambda: None)
    renderer = SimpleNamespace(
        rhi=_FakeRhi(),
        sampler=object(),
        tile_service=TileTextureService(max_tile_extent=max_tile_extent),
        host=host,
    )
    array_stub = _StubArrayResources(renderer.tile_service)
    rp.array_resources = array_stub
    return rp, renderer, array_stub


def _preview_qimage(w=100, h=80) -> QImage:
    image = QImage(w, h, QImage.Format.Format_RGBA8888)
    image.fill(0xFF804020)
    return image


def test_preview_to_full_swap_keeps_plain_until_promotion():
    rp, renderer, array_stub = _setup()
    preview = _preview_qimage()
    store = TiledPixelStore.from_pil(Image.new("RGBA", (1200, 800), "red"))
    try:
        rp.queue_upload(1, preview)
        rp.apply_pending_texture_ops(renderer, _FakeUpdates())
        assert 1 in rp.slot_resources.slot_textures

        rp.queue_upload(1, store)
        rp.apply_pending_texture_ops(renderer, _FakeUpdates())

        fallback = rp._last_good_key.get(1)
        assert fallback is not None and fallback != 1
        # No destroy-before-upload: the preview texture survives the swap.
        assert 1 in rp.slot_resources.slot_textures
        assert 1 in rp._pending_plain_cleanup
        # Backfilled into the array under the fallback key so the array
        # path can draw it underneath the new grid until covered.
        assert (fallback, (0, 0)) in array_stub.uploads
        assert renderer.tile_service.slot_for(fallback, (0, 0)) is not None
    finally:
        store.close()


def test_promotion_releases_stale_plain_preview_only():
    rp, renderer, _ = _setup()
    stale = _FakeTexture()
    rp.slot_resources.slot_textures[1] = stale
    rp.slot_resources.slot_texture_sizes[1] = (100, 80)
    rp._pending_plain_cleanup.add(1)

    # Non-promoting frame: untouched.
    rp._release_promoted_plain_preview(1, promoted_key="other", current_key=1)
    assert 1 in rp.slot_resources.slot_textures
    assert 1 in rp._pending_plain_cleanup

    # Promoting frame (new key fully uploaded): released + disarmed.
    rp._release_promoted_plain_preview(1, promoted_key=1, current_key=1)
    assert 1 not in rp.slot_resources.slot_textures
    assert 1 not in rp._pending_plain_cleanup


def test_small_to_small_swap_overwrites_same_frame():
    rp, renderer, _ = _setup()
    first = _preview_qimage()
    second = _preview_qimage()
    rp.queue_upload(1, first)
    rp.apply_pending_texture_ops(renderer, _FakeUpdates())
    assert 1 in rp.slot_resources.slot_textures

    rp.queue_upload(1, second)
    rp.apply_pending_texture_ops(renderer, _FakeUpdates())
    # Same-frame plain overwrite: drawable immediately, no deferred
    # cleanup left behind.
    assert 1 in rp.slot_resources.slot_textures
    assert 1 not in rp._pending_plain_cleanup


def test_duplicate_upload_is_noop_without_fallback():
    rp, renderer, _ = _setup()
    preview = _preview_qimage()
    rp.queue_upload(1, preview)
    rp.apply_pending_texture_ops(renderer, _FakeUpdates())

    rp.queue_upload(1, preview)
    rp.apply_pending_texture_ops(renderer, _FakeUpdates())
    assert rp._last_good_key.get(1) is None
    assert 1 not in rp._pending_plain_cleanup
