"""Fresh-preview backing for on-the-fly content changes.

The pyramid gate in ``pick_display_image`` gives the first-load path its
1024px preview backing while the pyramid builds. On-the-fly changes (swap,
next image, auto-crop resizing the store, a fresh preview arriving while
the previous unified store is still installed) can have a *complete*
pyramid already, so the canvas flips straight to store tiles and the
fallback-LOD baseline is the previous content -- the new preview never
appears. ``pick_display_with_preview_backing`` prefers the preview for the
stored role while it is fresh (its uid differs from the display pair last
applied), deferring the store flip by exactly one apply cycle so the flip's
fallback is the new preview's tiles.
"""

from __future__ import annotations

from PIL import Image

from shared.image_processing import pyramid_registry
from shared.image_processing.tiled_pixel_store import TiledPixelStore
from shared.rendering.image_identity import image_uid
from tabs.image_compare.presenters.image_canvas.background_parts.render_flow import (
    _display_cache_key,
    pick_display_with_preview_backing,
)


def _store(width=4096, height=4096):
    return TiledPixelStore.from_pil(Image.new("RGBA", (width, height), "red"))


def _complete_pyramid_store():
    pyramid_registry.clear()
    store = _store()
    pyramid = pyramid_registry.ensure_pyramid(store)
    pyramid.build_all()
    assert pyramid.is_complete()
    return store


def test_fresh_preview_wins_over_complete_pyramid_store():
    """A preview the canvas hasn't applied yet is the backing even when the
    store's pyramid is complete (the on-the-fly swap / crop-resize case)."""
    store = _complete_pyramid_store()
    preview = Image.new("RGBA", (1024, 683), "blue")
    try:
        picked = pick_display_with_preview_backing(
            store, preview, None, last_applied_uid=None
        )
        assert picked is preview
    finally:
        store.close()
        pyramid_registry.clear()


def test_already_applied_preview_flips_to_store():
    """Once the preview was applied (uid recorded), the next apply cycle
    picks the store as usual -- the flip still happens."""
    store = _complete_pyramid_store()
    preview = Image.new("RGBA", (1024, 683), "blue")
    try:
        picked = pick_display_with_preview_backing(
            store, preview, None, last_applied_uid=image_uid(preview)
        )
        assert picked is store
    finally:
        store.close()
        pyramid_registry.clear()


def test_fresh_preview_with_incomplete_pyramid_still_prefers_preview():
    pyramid_registry.clear()
    store = _store(4096, 4096)
    preview = Image.new("RGBA", (16, 16), "blue")
    try:
        pyramid = pyramid_registry.ensure_pyramid(store)
        assert not pyramid.is_complete()
        picked = pick_display_with_preview_backing(
            store, preview, None, last_applied_uid=None
        )
        assert picked is preview
    finally:
        store.close()
        pyramid_registry.clear()


def test_new_preview_replaces_stale_last_applied():
    """A newer preview (different uid) overrides a previously applied one."""
    store = _complete_pyramid_store()
    old_preview = Image.new("RGBA", (16, 16), "blue")
    new_preview = Image.new("RGBA", (32, 32), "green")
    try:
        picked = pick_display_with_preview_backing(
            store, new_preview, None, last_applied_uid=image_uid(old_preview)
        )
        assert picked is new_preview
    finally:
        store.close()
        pyramid_registry.clear()


def test_no_preview_keeps_pick_display_image_behavior():
    store = _complete_pyramid_store()
    try:
        assert pick_display_with_preview_backing(store, None, None) is store
    finally:
        store.close()
        pyramid_registry.clear()


def test_display_cache_key_shape_matches_presentation():
    """Stored-role ids must be a (uid1, uid2, size1, size2) 4-tuple like
    ``live_presentation.display_cache_key`` -- ``_textures_are_current``
    compares the next plan's key against ``_stored_image_ids`` verbatim."""
    img1 = Image.new("RGBA", (20, 10), "red")
    img2 = Image.new("RGBA", (10, 20), "blue")
    key = _display_cache_key(img1, img2)
    assert key == (image_uid(img1), image_uid(img2), (20, 10), (10, 20))