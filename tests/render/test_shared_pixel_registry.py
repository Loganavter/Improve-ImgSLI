"""Tests for engine.store.shared_pixel_registry (plan_shared_pixel_registry wave 1).

Every test asserts identity/content, never mere presence: shared views must
carry the requesting file's own bytes, stale/mismatched keys must miss, and
the spill file must die exactly at refcount zero.
"""

from __future__ import annotations

import os
import threading

import numpy as np
import pytest
from PIL import Image

from engine.cache.image_identity import image_uid
from engine.store import pyramid_registry, shared_pixel_registry as spr
from engine.store.shared_pixel_registry import SharedHandle
from engine.store.tiled_pixel_store import TiledPixelStore


@pytest.fixture(autouse=True)
def _clean_registries():
    spr.clear()
    pyramid_registry.clear()
    yield
    spr.clear()
    pyramid_registry.clear()


def _png(path, color=(10, 20, 30), size=(64, 48)):
    arr = np.zeros((size[1], size[0], 4), dtype=np.uint8)
    arr[:, :, 0] = color[0]
    arr[:, :, 1] = color[1]
    arr[:, :, 2] = color[2]
    arr[:, :, 3] = 255
    Image.fromarray(arr, mode="RGBA").save(str(path))
    return str(path)


def _payload(store) -> bytes:
    w, h = store.size
    return bytes(np.ascontiguousarray(store.read_array((0, 0, w, h))))


def _bump_mtime(path: str) -> None:
    st = os.stat(path)
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000))


def test_publish_acquire_shares_one_spill(tmp_path):
    p = _png(tmp_path / "a.png")
    base = TiledPixelStore.from_path(p)
    h1 = spr.publish(p, base)
    assert h1 is not None
    spill = h1.store.path
    assert spill is not None and os.path.exists(spill)

    h2 = spr.acquire(p)
    assert h2 is not None
    assert h2.store.path == spill  # one spill file on disk
    assert isinstance(h2.store, TiledPixelStore)
    assert not getattr(h2.store, "_owns_file", True)  # non-owning view
    assert _payload(h2.store) == _payload(h1.store)  # same bytes, not just same path
    assert spr.entry_count() == 1
    assert spr.live_refs() == 2

    spr.release(h1)
    assert os.path.exists(spill)  # refcount 1: spill survives
    assert h2.store.is_open
    spr.release(h2)
    assert spr.entry_count() == 0
    assert not os.path.exists(spill)  # delete exactly at zero


def test_close_one_view_keeps_other_readable(tmp_path):
    p = _png(tmp_path / "a.png")
    h1 = spr.publish(p, TiledPixelStore.from_path(p))
    h2 = spr.acquire(p)
    assert h1 is not None and h2 is not None
    want = _payload(h1.store)

    h1.store.close()  # unmigrated direct close(): detaches AND releases
    assert spr.live_refs() == 1
    assert _payload(h2.store) == want  # other view unaffected

    spr.release(h2)
    assert spr.entry_count() == 0


def test_release_none_and_double_release_safe(tmp_path):
    p = _png(tmp_path / "a.png")
    h1 = spr.publish(p, TiledPixelStore.from_path(p))
    h2 = spr.acquire(p)
    spr.release(None)
    spr.release(h1)
    spr.release(h1)  # idempotent: no double-decrement
    assert spr.live_refs() == 1
    spr.release(h2)
    assert spr.entry_count() == 0


def test_mtime_change_misses_and_republishes(tmp_path):
    p = _png(tmp_path / "a.png", color=(10, 20, 30))
    h1 = spr.publish(p, TiledPixelStore.from_path(p))
    assert h1 is not None

    _png(tmp_path / "a.png", color=(200, 10, 10))  # rewrite content
    _bump_mtime(p)
    assert spr.acquire(p) is None  # stale serve would be another tab's pixels

    h_new = spr.publish(p, TiledPixelStore.from_path(p))
    assert h_new is not None
    assert h_new.store.path != h1.store.path  # distinct spill per content
    assert _payload(h_new.store) != _payload(h1.store)  # identity, not presence
    assert spr.entry_count() == 2
    spr.release(h1)
    spr.release(h_new)
    assert spr.entry_count() == 0


def test_torn_publish_rejected_via_expected(tmp_path):
    p = _png(tmp_path / "a.png")
    st = os.stat(p)
    expected = (int(st.st_mtime_ns), int(st.st_size))
    decoded = TiledPixelStore.from_path(p)
    try:
        _png(tmp_path / "a.png", color=(200, 10, 10))  # changed mid-"decode"
        _bump_mtime(p)
        assert spr.publish(p, decoded, expected=expected) is None
        assert spr.entry_count() == 0
    finally:
        decoded.close()  # caller keeps ownership on publish refusal


def test_crop_mismatch_never_shares(tmp_path):
    p = _png(tmp_path / "a.png")
    h1 = spr.publish(p, TiledPixelStore.from_path(p), crop_fingerprint=None)
    assert h1 is not None
    assert spr.acquire(p, crop_fingerprint=(0, 0, 8, 8)) is None
    assert spr.acquire(p, crop_fingerprint="other-service") is None
    h2 = spr.acquire(p, crop_fingerprint=None)
    assert h2 is not None and h2.store.path == h1.store.path
    spr.release(h1)
    spr.release(h2)


def test_same_box_shares_across_service_instances(tmp_path):
    p = _png(tmp_path / "a.png")
    box = (4, 4, 60, 44)
    h1 = spr.publish(p, TiledPixelStore.from_path(p), crop_fingerprint=box)
    h2 = spr.acquire(p, crop_fingerprint=list(box))  # list form normalizes too
    assert h1 is not None and h2 is not None
    assert h2.store.path == h1.store.path
    spr.release(h1)
    spr.release(h2)


def test_concurrent_publish_collapses_to_one_entry(tmp_path):
    p = _png(tmp_path / "a.png")
    barrier = threading.Barrier(2)
    handles: list = [None, None]

    def _worker(i: int):
        barrier.wait(timeout=30)
        store = TiledPixelStore.from_path(p)
        handles[i] = spr.publish(p, store)
        if handles[i] is None:
            # Lost the race path is internal; publish either joins or owns.
            # A None here means fail-open — keep the direct store closed.
            try:
                store.close()
            except Exception:
                pass

    threads = [threading.Thread(target=_worker, args=(i,)) for i in (0, 1)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    assert all(h is not None for h in handles)
    assert spr.entry_count() == 1  # two decodes in, one entry survives
    assert handles[0].store.path == handles[1].store.path
    assert _payload(handles[0].store) == _payload(handles[1].store)
    spill = handles[0].store.path
    spr.release(handles[0])
    spr.release(handles[1])
    assert spr.entry_count() == 0
    assert not os.path.exists(spill)


def test_concurrent_acquires_all_readable(tmp_path):
    p = _png(tmp_path / "a.png")
    h0 = spr.publish(p, TiledPixelStore.from_path(p))
    assert h0 is not None
    want = _payload(h0.store)
    results: list = [None] * 4

    def _worker(i: int):
        h = spr.acquire(p)
        results[i] = (_payload(h.store) == want) if h is not None else False
        spr.release(h)

    threads = [threading.Thread(target=_worker, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    assert all(results)
    spr.release(h0)
    assert spr.entry_count() == 0


def test_bad_input_never_raises(tmp_path):
    assert spr.acquire("/nonexistent/imgsli.png") is None
    assert spr.acquire("", crop_fingerprint=(1, 2, 3)) is None  # bad box len
    assert spr.acquire("", crop_fingerprint=object()) is None
    p = _png(tmp_path / "a.png")
    assert spr.acquire(p, embedded_hit=True) is None  # embedded bypasses
    assert spr.publish(p, None) is None
    assert spr.publish(p, object()) is None  # type: ignore[arg-type]
    spr.release(None)
    spr.release(object())  # type: ignore[arg-type]
    spr.release(SharedHandle(store=None, generation_at_acquire=0))  # type: ignore[arg-type]
    assert spr.entry_count() == 0


def test_release_foreign_store_closes_like_today(tmp_path):
    p = _png(tmp_path / "a.png")
    direct = TiledPixelStore.from_path(p)
    spill = direct.path
    spr.release(SharedHandle(store=direct, generation_at_acquire=0))
    assert not direct.is_open
    assert not os.path.exists(spill)  # owning close deletes, as today
    assert spr.entry_count() == 0


def test_release_store_view_drops_ref_foreign_closes(tmp_path):
    p = _png(tmp_path / "a.png")
    h1 = spr.publish(p, TiledPixelStore.from_path(p))
    h2 = spr.acquire(p)
    assert h1 is not None and h2 is not None
    spr.release_store(h1.store)  # wave-3 tab path: raw store form
    assert spr.live_refs() == 1
    assert h2.store.is_open
    spr.release_store(None)
    spr.release_store(object())  # type: ignore[arg-type]
    direct = TiledPixelStore.from_path(p)
    spill = direct.path
    spr.release_store(direct)  # foreign: identical to close()
    assert not direct.is_open and not os.path.exists(spill)
    spr.release(h2)
    assert spr.entry_count() == 0


def test_views_share_uid_so_pyramids_dedupe(tmp_path):
    p = _png(tmp_path / "a.png")
    h1 = spr.publish(p, TiledPixelStore.from_path(p))
    h2 = spr.acquire(p)
    assert h1 is not None and h2 is not None
    assert image_uid(h1.store) == image_uid(h2.store)
    pyr1 = pyramid_registry.ensure_pyramid(h1.store)
    pyr2 = pyramid_registry.ensure_pyramid(h2.store)
    assert pyr1 is not None and pyr2 is pyr1  # one pyramid base, not two
    spr.release(h1)
    spr.release(h2)


# --- Wave 2: funnel interception (load_pixel_store) ---


def test_funnel_same_file_two_sessions_one_spill(tmp_path):
    from shared.image_processing.pixel_cache_loader import load_pixel_store

    p = _png(tmp_path / "shared.png", color=(40, 50, 60))
    s1 = load_pixel_store(p)
    s2 = load_pixel_store(p)
    try:
        assert isinstance(s1, TiledPixelStore) and isinstance(s2, TiledPixelStore)
        assert s1.path == s2.path  # one spill file on disk, not two
        assert _payload(s1) == _payload(s2)
        assert spr.entry_count() == 1
    finally:
        s1.close()
        s2.close()
    assert spr.entry_count() == 0
    assert not os.path.exists(s1.path or "")


def test_funnel_decodes_once_for_two_sessions(tmp_path, monkeypatch):
    from shared.image_processing import pixel_cache_loader as pcl

    p = _png(tmp_path / "once.png", color=(70, 80, 90))
    calls = []
    real_from_path = TiledPixelStore.from_path

    @classmethod
    def _counting_from_path(cls, path, *args, **kwargs):
        calls.append(str(path))
        return real_from_path(path, *args, **kwargs)

    monkeypatch.setattr(TiledPixelStore, "from_path", _counting_from_path)
    s1 = pcl.load_pixel_store(p)
    s2 = pcl.load_pixel_store(p)
    try:
        assert len(calls) == 1  # second session hits the registry, no decode
        assert s1.path == s2.path
    finally:
        s1.close()
        s2.close()


def test_funnel_probe_failure_bypasses_registry(tmp_path):
    from shared.image_processing.pixel_cache_loader import load_pixel_store

    class _FailingCrop:
        def get(self, path):
            raise RuntimeError("probe exploded")

    p = _png(tmp_path / "probefail.png", color=(11, 22, 33))
    s1 = load_pixel_store(p, crop_service=_FailingCrop())
    s2 = load_pixel_store(p, crop_service=_FailingCrop())
    try:
        # Unknown crop state must never share: two independent spills.
        assert s1.path != s2.path
        assert _payload(s1) == _payload(s2)  # same file, same bytes
        assert spr.entry_count() == 0
    finally:
        s1.close()
        s2.close()


def test_funnel_distinct_boxes_never_share(tmp_path):
    from shared.image_processing.autocrop.model import CropBox
    from shared.image_processing.pixel_cache_loader import load_pixel_store

    class _CannedCrop:
        def __init__(self, box):
            self._box = box

        def get(self, path):
            return self._box

    p = _png(tmp_path / "boxes.png", color=(44, 55, 66))
    s_none = load_pixel_store(p, crop_service=None)
    s_box = load_pixel_store(
        p, crop_service=_CannedCrop(CropBox(0, 0, 32, 24))
    )
    try:
        assert s_none.path != s_box.path  # cropped pixels ≠ full pixels
        assert s_box.size == (32, 24)
        assert spr.entry_count() == 2
    finally:
        s_none.close()
        s_box.close()
    assert spr.entry_count() == 0
