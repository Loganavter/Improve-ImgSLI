"""Compare-unify parity: multi_compare side of the frozen loading seam.

Exercises ONLY the frozen seam (``tabs._shared.loading_pipeline`` —
never re-implemented here) from the multi_compare point of view:
boxless key parity with ``MultiComparePixelCache``, arbitrary slot ids
as the index, sparse/evicted slots as gaps (``resolve`` parity), and
fail-closed misses. Offscreen-Qt compatible, no live RHI —
data/identity only.

Seam under test: ``src/tabs/_shared/loading_pipeline.py``.
Tab-local contrast: ``src/tabs/multi_compare/pipeline/cache.py``
(tree/gap/``NoteSlotPixels`` stay tab-local; see
``../docs/compare_unify_parity.md``).
"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtGui import QColor, QImage

from tabs._shared import loading_pipeline as seam
from tabs._shared.loading_pipeline import (
    _same_fs_path,
    cache_key_for_path,
    ensure_async,
    get_or_load_pixel,
    get_or_load_preview,
    pick_display_image,
    start_pyramid_build,
)


@pytest.fixture(autouse=True)
def _sync_seam(monkeypatch):
    """Force the headless sync shape: no thread pool, clean registries."""
    monkeypatch.setattr(seam, "_global_thread_pool", lambda: None)
    saved_preview = dict(seam._preview_inflight)
    saved_active = dict(seam._full_active)
    saved_queue = list(seam._full_queue)
    seam._preview_inflight.clear()
    seam._full_active.clear()
    seam._full_queue.clear()
    try:
        yield
    finally:
        seam._preview_inflight.clear()
        seam._preview_inflight.update(saved_preview)
        seam._full_active.clear()
        seam._full_active.update(saved_active)
        seam._full_queue.clear()
        seam._full_queue.extend(saved_queue)


class _FakeCache:
    """Path-keyed stand-in for ``MultiComparePixelCache`` tiers."""

    def __init__(self):
        self.previews: dict[str, object] = {}
        self.pixels: dict[str, object] = {}

    def get_preview(self, path):
        return self.previews.get(str(path))

    def put_preview(self, path, qimage):
        self.previews[str(path)] = qimage

    def get_pixel(self, path):
        return self.pixels.get(str(path))

    def put_pixel(self, path, store):
        self.pixels[str(path)] = store


class _FakeStore:
    """Minimal usable-pixel stand-in (``is_open`` protocol only)."""

    def __init__(self, tag, *, open=True):
        self.tag = tag
        self._open = open

    def is_open(self):
        return self._open


def _color_image(r, g, b):
    img = QImage(8, 8, QImage.Format.Format_RGBA8888)
    img.fill(QColor(r, g, b))
    assert not img.isNull()
    return img


def _write_file(path: Path, payload: bytes = b"x") -> Path:
    path.write_bytes(payload)
    return path


# --- key shape: (normpath, mtime_ns, size), boxless ---


def test_key_shape_is_normpath_mtime_size_boxless(tmp_path):
    f = _write_file(tmp_path / "slot0.png", b"0123456789")
    key = cache_key_for_path(f)
    st = os.stat(os.path.normpath(str(f)))
    assert key == (os.path.normpath(str(f)), st.st_mtime_ns, st.st_size)
    assert len(key) == 3, "boxless: no crop/box 4th element"


def test_key_heals_textual_variants_never_equates_distinct(tmp_path):
    f = _write_file(tmp_path / "slot0.png", b"data")
    dotted = os.path.join(str(tmp_path), ".", "slot0.png")
    assert cache_key_for_path(dotted) == cache_key_for_path(f)
    assert cache_key_for_path(str(f)) == cache_key_for_path(Path(f))
    assert _same_fs_path(dotted, f)
    other = _write_file(tmp_path / "slot1.png", b"data")
    assert cache_key_for_path(other) != cache_key_for_path(f)
    assert not _same_fs_path(str(f), str(other))


def test_key_missing_file_fails_closed(tmp_path):
    missing = tmp_path / "ghost.png"
    assert cache_key_for_path(missing) == (os.path.normpath(str(missing)), 0, 0)


def test_key_matches_mc_cache_key_constructor(tmp_path):
    """Seam key == tab ``cache_key_for_path`` for the same file."""
    from tabs.multi_compare.pipeline.cache import cache_key_for_path as mc_key

    f = _write_file(tmp_path / "slot0.png", b"mc-parity")
    assert mc_key(f) == cache_key_for_path(f)
    assert mc_key(str(f)) == cache_key_for_path(Path(f))


def test_overwrite_in_place_changes_key_no_stale_collision(tmp_path):
    f = _write_file(tmp_path / "slot0.png", b"v1-payload!!")
    before = cache_key_for_path(f)
    f.write_bytes(b"v2-payload!!-longer")
    after = cache_key_for_path(f)
    assert before[0] == after[0]
    assert before != after, "mtime+size keeps the rewrite from colliding with stale decode"


# --- delegation: usable tiers come back, cached on second call ---


def test_preview_delegation_returns_usable_tier_and_caches(monkeypatch, tmp_path):
    import shared.image_processing.progressive_loader as pl

    f = _write_file(tmp_path / "slot0.png", b"img")
    expected = _color_image(30, 10, 200)
    calls: list[str] = []

    def _fake_preview(path):
        calls.append(str(path))
        return expected

    monkeypatch.setattr(pl, "load_preview_image", _fake_preview)
    cache = _FakeCache()
    got = get_or_load_preview(cache, f)
    assert got is expected
    assert cache.get_preview(str(f)) is expected
    assert get_or_load_preview(cache, f) is expected, "second call served from cache"
    assert len(calls) == 1, "no re-decode on cache hit"


def test_pixel_delegation_returns_usable_tier_and_caches(monkeypatch, tmp_path):
    import shared.image_processing.pixel_cache_loader as pcl

    f = _write_file(tmp_path / "slot0.png", b"img")
    expected = _FakeStore("mc-full")
    monkeypatch.setattr(pcl, "load_pixel_store", lambda path, **kw: expected)
    cache = _FakeCache()
    got = get_or_load_pixel(cache, f)
    assert got is expected
    assert cache.get_pixel(str(f)) is expected
    assert get_or_load_pixel(cache, f) is expected


# --- miss fails closed to None, never a neighbor payload ---


def test_preview_miss_fails_closed_to_none(monkeypatch, tmp_path):
    import shared.image_processing.progressive_loader as pl

    good = _write_file(tmp_path / "slot0.png", b"good")
    bad = tmp_path / "slot1.png"
    neighbor = _color_image(10, 200, 10)
    cache = _FakeCache()
    cache.put_preview(str(good), neighbor)

    def _boom(path):
        raise RuntimeError("decode exploded")

    monkeypatch.setattr(pl, "load_preview_image", _boom)
    assert get_or_load_preview(cache, bad) is None
    assert get_or_load_preview(None, bad) is None
    assert str(bad) not in cache.previews, "miss must not plant anything"
    assert cache.get_preview(str(good)) is neighbor, "neighbor tier untouched"


def test_pixel_miss_fails_closed_to_none(monkeypatch, tmp_path):
    import shared.image_processing.pixel_cache_loader as pcl

    bad = tmp_path / "slot9.png"
    monkeypatch.setattr(pcl, "load_pixel_store", lambda path, **kw: None)
    assert get_or_load_pixel(_FakeCache(), bad) is None

    def _boom(path, **kw):
        raise OSError("unreadable")

    monkeypatch.setattr(pcl, "load_pixel_store", _boom)
    assert get_or_load_pixel(_FakeCache(), bad) is None


def test_mc_resolve_gap_agrees_with_seam_miss(tmp_path):
    """Imageless slot: tab ``resolve`` and seam miss both read as gap."""
    from tabs.multi_compare.pipeline.cache import MultiComparePixelCache

    cache = MultiComparePixelCache()
    missing = tmp_path / "slot-missing.png"
    assert cache.resolve(missing) is None
    assert cache.resolve(None) is None
    slot = SimpleNamespace(path=missing)
    from tabs.multi_compare.pipeline.cache import resolve_slot_source

    assert resolve_slot_source(cache, slot) is None
    assert resolve_slot_source(None, slot) is None


# --- distinct-content probe: payload(i) == content(i) per index ---


def test_distinct_content_probe_preview_identity_per_slot(monkeypatch, tmp_path):
    """N distinguishable previews: each slot resolves its own content.

    Counts/sizes alone are rejected as correctness — every slot asserts
    its exact pixel color.
    """
    import shared.image_processing.progressive_loader as pl

    colors = [(200, 30, 30), (30, 200, 30), (30, 30, 200), (200, 200, 30), (30, 200, 200)]
    files = [_write_file(tmp_path / f"slot{i}.png", bytes([i + 2]) * 8) for i in range(5)]
    palette = {str(p): _color_image(*c) for p, c in zip(files, colors)}
    monkeypatch.setattr(pl, "load_preview_image", lambda path: palette[str(path)])
    cache = _FakeCache()
    for i, path in enumerate(files):
        got = get_or_load_preview(cache, path)
        want = QColor(*colors[i])
        assert got.pixelColor(0, 0) == want, f"slot {i}: payload must equal content({i})"
    assert len(cache.previews) == 5


def test_distinct_content_probe_pixel_identity_per_slot(monkeypatch, tmp_path):
    import shared.image_processing.pixel_cache_loader as pcl

    files = [_write_file(tmp_path / f"full{i}.png", bytes([i + 1]) * 8) for i in range(4)]
    stores = {str(p): _FakeStore(f"content-{i}") for i, p in enumerate(files)}
    monkeypatch.setattr(pcl, "load_pixel_store", lambda path, **kw: stores[str(path)])
    cache = _FakeCache()
    for i, path in enumerate(files):
        got = get_or_load_pixel(cache, path)
        assert got is stores[str(path)]
        assert got.tag == f"content-{i}", f"slot {i}: payload must equal content({i})"


# --- sparse / evicted / stale-after-fresh: gap, never neighbor ---


def test_sparse_slot_is_gap_not_neighbor(monkeypatch, tmp_path):
    import shared.image_processing.progressive_loader as pl

    monkeypatch.setattr(pl, "load_preview_image", lambda path: None)
    cache = _FakeCache()
    cache.put_preview(str(tmp_path / "slot0.png"), _color_image(9, 9, 9))
    assert get_or_load_preview(cache, tmp_path / "slot7.png") is None


def test_evicted_slot_returns_to_gap(tmp_path):
    """Tab-cache evict drops all tiers; seam-side the slot reads as gap."""
    from tabs.multi_compare.pipeline.cache import MultiComparePixelCache

    cache = MultiComparePixelCache()
    f = _write_file(tmp_path / "slot0.png", b"evict-me")
    store = _FakeStore("doomed")
    cache.put_pixel(f, store)
    cache.put_preview(f, _color_image(1, 2, 3))
    assert cache.get_pixel(f) is store
    cache.evict(f)
    assert cache.get_pixel(f) is None
    assert cache.get_preview(f) is None
    assert cache.resolve(f) is None, "evicted slot is a gap, not a stale payload"


def test_stale_cached_tiers_read_as_miss(tmp_path):
    cache = _FakeCache()
    cache.put_pixel("slot-stale.png", _FakeStore("closed", open=False))
    null_img = QImage()
    assert null_img.isNull()
    cache.put_preview("slot-stale.png", null_img)
    assert seam._is_usable_pixel(cache.get_pixel("slot-stale.png")) is False
    assert seam._is_usable_preview(cache.get_preview("slot-stale.png")) is False


def test_stale_after_fresh_key_diverges_and_fresh_wins(monkeypatch, tmp_path):
    import shared.image_processing.progressive_loader as pl

    f = _write_file(tmp_path / "slot0.png", b"fresh-v1!!")
    stale_key = cache_key_for_path(f)
    f.write_bytes(b"fresh-v2!!-changed-length")
    fresh_key = cache_key_for_path(f)
    assert stale_key != fresh_key
    fresh_img = _color_image(99, 11, 44)
    monkeypatch.setattr(pl, "load_preview_image", lambda path: fresh_img)
    cache = _FakeCache()
    assert get_or_load_preview(cache, f) is fresh_img


# --- index in cache keys: slot ids route to their own slot ---


def test_ensure_async_delivers_per_slot_ids_with_own_payloads(monkeypatch, tmp_path):
    """Arbitrary slot ids (3, 7): distinct files never cross (slot id is
    part of the async routing key)."""
    import shared.image_processing.pixel_cache_loader as pcl
    import shared.image_processing.progressive_loader as pl

    a = _write_file(tmp_path / "a.png", b"aaa-payload")
    b = _write_file(tmp_path / "b.png", b"bbb-PAYLOAD")
    c = _write_file(tmp_path / "c.png", b"ccc-payload")
    previews = {
        str(a): _color_image(210, 40, 40),
        str(b): _color_image(40, 210, 40),
        str(c): _color_image(40, 40, 210),
    }
    fulls = {str(p): _FakeStore(f"full-{n}") for p, n in ((a, "a"), (b, "b"), (c, "c"))}
    monkeypatch.setattr(pl, "load_preview_image", lambda path: previews[str(path)])
    monkeypatch.setattr(pcl, "load_pixel_store", lambda path, **kw: fulls.get(str(path)))

    cache = _FakeCache()
    seen: list[tuple] = []
    for path, sid in ((a, 3), (b, 7), (c, 12)):
        ensure_async(cache, path, sid, on_ready=lambda s, p, obj: seen.append((s, str(p), obj)))
    by_slot = {sid: (p, obj) for sid, p, obj in seen}
    assert set(by_slot) == {3, 7, 12}, "every slot id delivered"
    assert by_slot[3][0] == str(a) and by_slot[7][0] == str(b) and by_slot[12][0] == str(c)
    for sid, (p, obj) in by_slot.items():
        assert obj is previews[p] or obj is fulls[p], f"slot {sid}: own payload only"
    assert all(obj is not previews[str(b)] for sid, _, obj in seen if sid == 3)
    assert all(obj is not previews[str(a)] for sid, _, obj in seen if sid == 7)


def test_ensure_async_same_file_fans_out_to_each_slot(monkeypatch, tmp_path):
    import shared.image_processing.pixel_cache_loader as pcl
    import shared.image_processing.progressive_loader as pl

    f = _write_file(tmp_path / "shared.png", b"shared")
    img = _color_image(15, 16, 17)
    monkeypatch.setattr(pl, "load_preview_image", lambda path: img)
    monkeypatch.setattr(pcl, "load_pixel_store", lambda path, **kw: _FakeStore("shared-full"))
    cache = _FakeCache()
    seen: list[tuple] = []
    ensure_async(cache, f, 3, on_ready=lambda sid, p, obj: seen.append((sid, obj)))
    ensure_async(cache, f, 7, on_ready=lambda sid, p, obj: seen.append((sid, obj)))
    assert {sid for sid, _ in seen} == {3, 7}
    assert all(obj is img or getattr(obj, "tag", None) == "shared-full" for _, obj in seen)


def test_ensure_async_miss_calls_on_error_never_neighbor(monkeypatch, tmp_path):
    import shared.image_processing.pixel_cache_loader as pcl
    import shared.image_processing.progressive_loader as pl

    good = _write_file(tmp_path / "slot0.png", b"good")
    bad = tmp_path / "slot-bad.png"
    neighbor = _color_image(10, 200, 10)
    cache = _FakeCache()
    cache.put_preview(str(good), neighbor)

    def _boom_preview(path):
        if str(path) == str(bad):
            raise RuntimeError("no decode")
        return neighbor

    def _boom_full(path, **kw):
        raise RuntimeError("no full decode")

    monkeypatch.setattr(pl, "load_preview_image", _boom_preview)
    monkeypatch.setattr(pcl, "load_pixel_store", _boom_full)
    ready: list = []
    errors: list = []
    ensure_async(
        cache,
        bad,
        7,
        on_ready=lambda sid, p, obj: ready.append((sid, obj)),
        on_error=lambda sid, p, err: errors.append((sid, err)),
    )
    assert ready == [], "miss must never deliver — not even the neighbor tier"
    assert [sid for sid, _ in errors] == [7]


def test_sizes_for_slots_keys_include_slot_index(monkeypatch, tmp_path):
    """Dispatch helper maps ``{slot_id: (w, h)}`` — the index is in the key."""
    import engine.store.tiled_pixel_store as tps
    from tabs.multi_compare.pipeline.cache import MultiComparePixelCache, sizes_for_slots

    f0 = _write_file(tmp_path / "s0.png", b"s0")
    f1 = _write_file(tmp_path / "s1.png", b"s1")
    cache = MultiComparePixelCache()
    cache.put_pixel(f0, _FakeStore("s0"))
    cache.put_pixel(f1, _FakeStore("s1"))
    dims = {(f0, "s0"): (640, 480), (f1, "s1"): (800, 600)}

    def _fake_size(source):
        for (path, tag), size in dims.items():
            if getattr(source, "tag", None) == tag:
                return size
        return (0, 0)

    monkeypatch.setattr(tps, "pixel_source_size", _fake_size)
    slots = [SimpleNamespace(id=3, path=f0), SimpleNamespace(id=7, path=f1)]
    assert sizes_for_slots(cache, slots) == {3: (640, 480), 7: (800, 600)}
    assert sizes_for_slots(None, slots) is None


# --- picking + pyramid hook: fail-open, usable tiers first ---


def test_pick_display_image_prefers_first_real_and_gaps_to_none():
    preview = _color_image(33, 22, 11)
    assert pick_display_image(None, preview) is preview
    assert pick_display_image(None, None) is None
    assert pick_display_image() is None


def test_start_pyramid_build_fail_open():
    start_pyramid_build(None, 3, None)
    start_pyramid_build(_FakeStore("x"), 3, None)

    def _boom(store, slot_id):
        raise RuntimeError("toast exploded")

    start_pyramid_build(_FakeStore("x"), 3, _boom)  # must not raise
