"""The display (stored) role must not pick a TiledPixelStore whose mipmap
pyramid is not complete yet.

Regression this guards: after the display cache was removed, the unified
TiledPixelStore reached the canvas before its pyramid was built. With no
coarse level available, ``resolve_lod_texture_keys`` fell back to the bare
level-0 key and the renderer cropped+uploaded every 8192-square tile of a
20k pair (12+ seconds, 81 draw calls) just to show the overview. The picker
must keep the preview tier on screen until the pyramid builder finishes.
"""

from __future__ import annotations

from PIL import Image

from shared.image_processing import pyramid_registry
from shared.image_processing.tiled_pixel_store import TiledPixelStore
from shared.rendering.display_image_picker import pick_display_image


def _store(width=64, height=64):
    return TiledPixelStore.from_pil(Image.new("RGBA", (width, height), "red"))


def test_store_without_pyramid_falls_back_to_preview():
    pyramid_registry.clear()
    store = _store()
    preview = Image.new("RGBA", (16, 16), "blue")
    try:
        assert pick_display_image(store, preview) is preview
    finally:
        store.close()
        pyramid_registry.clear()


def test_store_with_incomplete_pyramid_falls_back_to_preview():
    pyramid_registry.clear()
    store = _store(4096, 4096)
    preview = Image.new("RGBA", (16, 16), "blue")
    try:
        pyramid = pyramid_registry.ensure_pyramid(store)
        assert not pyramid.is_complete()
        assert pick_display_image(store, preview) is preview
    finally:
        store.close()
        pyramid_registry.clear()


def test_store_with_complete_pyramid_is_picked():
    pyramid_registry.clear()
    store = _store(4096, 4096)
    preview = Image.new("RGBA", (16, 16), "blue")
    try:
        pyramid = pyramid_registry.ensure_pyramid(store)
        pyramid.build_all()
        assert pyramid.is_complete()
        assert pick_display_image(store, preview) is store
    finally:
        store.close()
        pyramid_registry.clear()


def test_tiny_store_is_ready_once_registered():
    pyramid_registry.clear()
    store = _store(64, 64)  # <= COARSEST_MIN_DIM: pyramid complete at birth
    try:
        pyramid_registry.ensure_pyramid(store)
        assert pick_display_image(store, None) is store
    finally:
        store.close()
        pyramid_registry.clear()


def test_unready_store_without_preview_still_renders():
    """A slow first frame beats a blank canvas when there is no fallback."""
    pyramid_registry.clear()
    store = _store()
    try:
        assert pick_display_image(store, None) is store
    finally:
        store.close()
        pyramid_registry.clear()


def test_plain_pil_image_is_unaffected():
    image = Image.new("RGBA", (8, 8), "green")
    assert pick_display_image(None, image) is image
