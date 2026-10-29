"""The video editor's image repository reuses the session's decoded spill.

Opening the video editor used to re-decode the source frames even though the
Image Compare tab already held them: ``get_image(path, auto_crop=False)``
must look the store up in ``engine.store.shared_pixel_registry`` under the IC
publish key (``crop_fingerprint=None``) and only decode on a miss. A hit is a
non-owning view — the repository tracks it and releases the registry ref when
it clears its cache, without touching the tab's spill.

Structure, no timings: which store identity is served, whether
``TiledPixelStore.from_path`` ran, and which lifecycle call ends the entry.
"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from engine.cache.image_identity import image_uid
from engine.store import pyramid_registry, shared_pixel_registry as spr
from engine.store.tiled_pixel_store import TiledPixelStore
from tabs.image_compare.plugins.video_editor.services.video_export import (
    images as images_mod,
)


@pytest.fixture(autouse=True)
def _clean_registries():
    spr.clear()
    pyramid_registry.clear()
    yield
    spr.clear()
    pyramid_registry.clear()


def _png(path, *, color=(10, 20, 30), size=(64, 48)):
    arr = np.zeros((size[1], size[0], 4), dtype=np.uint8)
    arr[:, :, 0] = color[0]
    arr[:, :, 1] = color[1]
    arr[:, :, 2] = color[2]
    arr[:, :, 3] = 255
    Image.fromarray(arr, mode="RGBA").save(str(path))
    return str(path)


def _payload(store) -> bytes:
    w, h = store.size
    return np.ascontiguousarray(store.read_array((0, 0, w, h))).tobytes()


def _publish_as_ic_tab(path):
    """Publish ``path`` exactly like the IC tab's decode funnel does (no crop)."""
    from shared.image_processing.pixel_cache_loader import load_pixel_store

    store = load_pixel_store(path)
    assert spr.entry_count() == 1
    return store


def test_get_image_reuses_the_published_session_store(tmp_path, monkeypatch):
    """A hit serves the published decode: same uid/content/pyramid, no decode."""
    path = _png(tmp_path / "frame.png")
    published = _publish_as_ic_tab(path)
    published_uid = image_uid(published)

    def _boom(*_args, **_kwargs):
        raise AssertionError("must reuse the session store, not decode again")

    monkeypatch.setattr(images_mod.TiledPixelStore, "from_path", _boom)

    repo = images_mod.VideoExportImageRepository()
    store = repo.get_image(path, False)

    assert store is not None and store is not published
    # Same spill, same pixels, same identity tag (pyramid dedup depends on it).
    assert image_uid(store) == published_uid
    assert store.path == published.path
    assert _payload(store) == _payload(published)

    pyramid = pyramid_registry.ensure_pyramid(published)
    assert pyramid is not None
    assert pyramid_registry.pyramid_for(store) is pyramid

    assert repo._images_cache[(path, False)] is store
    assert (path, False) in repo._shared_views


@pytest.mark.parametrize(
    "acquire_behaviour",
    ["raises", "none", "none_store"],
)
def test_registry_miss_or_failure_falls_back_to_decode(
    tmp_path, monkeypatch, acquire_behaviour
):
    """Fail-open: empty/raising/None-handle registry == today's from_path."""
    path = _png(tmp_path / "frame.png")
    assert spr.entry_count() == 0

    def _acquire(*_args, **_kwargs):
        if acquire_behaviour == "raises":
            raise RuntimeError("registry down")
        if acquire_behaviour == "none":
            return None
        return SimpleNamespace(store=None)

    monkeypatch.setattr(spr, "acquire", _acquire)

    decoded = object()
    calls: list = []

    def _from_path(p, auto_crop=False):
        calls.append((p, auto_crop))
        return decoded

    monkeypatch.setattr(images_mod.TiledPixelStore, "from_path", _from_path)

    repo = images_mod.VideoExportImageRepository()
    assert repo.get_image(path, False) is decoded
    assert calls == [(path, False)]
    assert repo._shared_views == set()


def test_crop_fingerprint_entry_is_never_served_to_the_no_crop_lookup(
    tmp_path, monkeypatch
):
    """A box-keyed entry is different content; the no-crop key must miss."""
    path = _png(tmp_path / "frame.png")
    base = TiledPixelStore.from_path(path)
    handle = spr.publish(path, base, crop_fingerprint=(1, 2, 40, 30))
    assert handle is not None

    decoded = object()
    calls: list = []

    def _from_path(p, auto_crop=False):
        calls.append((p, auto_crop))
        return decoded

    monkeypatch.setattr(images_mod.TiledPixelStore, "from_path", _from_path)

    repo = images_mod.VideoExportImageRepository()
    assert repo.get_image(path, False) is decoded
    assert calls == [(path, False)]
    assert (path, False) not in repo._shared_views


def test_auto_crop_never_consults_the_registry(tmp_path, monkeypatch):
    """auto_crop=True needs the crop box first; it decodes as before."""
    path = _png(tmp_path / "frame.png")
    _publish_as_ic_tab(path)  # a no-crop hit WOULD exist for auto_crop=False

    consulted: list = []

    def _acquire(*args, **kwargs):
        consulted.append((args, kwargs))
        raise AssertionError("auto_crop=True must not consult the registry")

    monkeypatch.setattr(spr, "acquire", _acquire)

    decoded = object()
    monkeypatch.setattr(
        images_mod.TiledPixelStore,
        "from_path",
        lambda p, auto_crop=False: decoded,
    )

    repo = images_mod.VideoExportImageRepository()
    assert repo.get_image(path, True) is decoded
    assert consulted == []
    assert repo._shared_views == set()


def test_clear_releases_cached_shared_views(tmp_path):
    """The repository's cache drop must release the ref, never close the base."""
    path = _png(tmp_path / "frame.png")
    published = _publish_as_ic_tab(path)
    assert spr.live_refs() == 1  # the funnel's own handle

    repo = images_mod.VideoExportImageRepository()
    view = repo.get_image(path, False)
    assert view is not None and view is not published
    assert spr.live_refs() == 2  # repository holds one more view

    repo.clear()

    assert spr.live_refs() == 1  # released, refcount back to the tab's hold
    assert spr.entry_count() == 1  # tab's spill + pixels survive
    assert published.is_open is True
    assert view.is_open is False  # the view itself detached
    assert repo._images_cache == {}
    assert repo._shared_views == set()


def test_clear_leaves_a_directly_decoded_store_alone(tmp_path):
    """Miss path keeps today's lifecycle: the decode owner closes its store."""
    path = _png(tmp_path / "frame.png")

    repo = images_mod.VideoExportImageRepository()
    store = repo.get_image(path, False)

    assert isinstance(store, TiledPixelStore) and store.is_open
    assert spr.entry_count() == 0  # a direct decode publishes nothing
    assert repo._shared_views == set()

    repo.clear()

    assert store.is_open is True  # clear() does not close foreign stores
    store.close()
