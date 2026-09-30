"""Compare-unify parity: image_compare side of the frozen loading seam.

Exercises ONLY the frozen seam (``tabs._shared.loading_pipeline`` —
never re-implemented here) from the image_compare point of view:
boxless key parity with ``PipelineCache`` pixel/preview shapes, divider
sides (slot 0/1) as the index, preview-then-full convergence, and
fail-closed misses. Offscreen-Qt compatible, no live RHI — data/identity
only.

Seam under test: ``src/tabs/_shared/loading_pipeline.py``.
Tab-local contrast: ``src/tabs/image_compare/pipeline/cache.py``
(unify tier + divider stay tab-local; see ``../docs/compare_unify_parity.md``).
"""

from __future__ import annotations

import os
from pathlib import Path

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
    queue_full_resolution,
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
    """Path-keyed stand-in for the tab pixel cache (preview + pixel tiers)."""

    def __init__(self):
        self.previews: dict[str, object] = {}
        self.pixels: dict[str, object] = {}
        self.decode_calls = 0

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
    f = _write_file(tmp_path / "a.png", b"0123456789")
    key = cache_key_for_path(f)
    st = os.stat(os.path.normpath(str(f)))
    assert key == (os.path.normpath(str(f)), st.st_mtime_ns, st.st_size)
    assert len(key) == 3, "boxless: no crop/box 4th element"


def test_key_heals_textual_variants_never_equates_distinct(tmp_path):
    f = _write_file(tmp_path / "a.png", b"data")
    dotted = os.path.join(str(tmp_path), ".", "a.png")
    assert cache_key_for_path(dotted) == cache_key_for_path(f)
    assert cache_key_for_path(str(f)) == cache_key_for_path(Path(f))
    assert _same_fs_path(dotted, f)
    assert _same_fs_path(str(f), Path(f))
    other = _write_file(tmp_path / "b.png", b"data")
    assert cache_key_for_path(other) != cache_key_for_path(f)
    assert not _same_fs_path(str(f), str(other))


def test_key_missing_file_fails_closed(tmp_path):
    missing = tmp_path / "nope.png"
    assert cache_key_for_path(missing) == (os.path.normpath(str(missing)), 0, 0)


def test_key_matches_ic_pipeline_cache_content_part(tmp_path):
    """First three elements agree with PipelineCache boxless keys."""
    from tabs.image_compare.pipeline.cache import _pixel_key, _preview_key

    f = _write_file(tmp_path / "a.png", b"ic-parity")
    key = cache_key_for_path(f)
    assert _pixel_key(str(f))[:3] == key
    assert _preview_key(str(f))[:3] == key
    assert _pixel_key(str(f))[3] is False, "tab key stays boxless (False slot)"


def test_overwrite_in_place_changes_key_no_stale_collision(tmp_path):
    f = _write_file(tmp_path / "a.png", b"v1-payload!!")
    before = cache_key_for_path(f)
    f.write_bytes(b"v2-payload!!-longer")
    after = cache_key_for_path(f)
    assert before[0] == after[0]
    assert before != after, "mtime+size keeps the rewrite from colliding with stale decode"


# --- delegation: usable tiers come back, cached on second call ---


def test_preview_delegation_returns_usable_tier_and_caches(monkeypatch, tmp_path):
    import shared.image_processing.progressive_loader as pl

    f = _write_file(tmp_path / "a.png", b"img")
    expected = _color_image(10, 20, 30)
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

    f = _write_file(tmp_path / "a.png", b"img")
    expected = _FakeStore("ic-full")
    monkeypatch.setattr(pcl, "load_pixel_store", lambda path, **kw: expected)
    cache = _FakeCache()
    got = get_or_load_pixel(cache, f)
    assert got is expected
    assert cache.get_pixel(str(f)) is expected
    assert get_or_load_pixel(cache, f) is expected


# --- miss fails closed to None, never a neighbor payload ---


def test_preview_miss_fails_closed_to_none(monkeypatch, tmp_path):
    import shared.image_processing.progressive_loader as pl

    good = _write_file(tmp_path / "good.png", b"good")
    bad = tmp_path / "bad.png"
    neighbor = _color_image(200, 10, 10)
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

    bad = tmp_path / "bad.png"
    monkeypatch.setattr(pcl, "load_pixel_store", lambda path, **kw: None)
    assert get_or_load_pixel(_FakeCache(), bad) is None

    def _boom(path, **kw):
        raise OSError("unreadable")

    monkeypatch.setattr(pcl, "load_pixel_store", _boom)
    assert get_or_load_pixel(_FakeCache(), bad) is None


def test_stale_cached_tiers_read_as_miss(tmp_path):
    """Closed store / null QImage in cache behave as gap, not payload."""
    cache = _FakeCache()
    cache.put_pixel("stale.png", _FakeStore("closed", open=False))
    null_img = QImage()
    assert null_img.isNull()
    cache.put_preview("stale.png", null_img)
    # Seam usability gates reject both without decode; emulate the gate
    # outcome the seam applies before returning a cached tier.
    assert seam._is_usable_pixel(cache.get_pixel("stale.png")) is False
    assert seam._is_usable_preview(cache.get_preview("stale.png")) is False


# --- distinct-content probe: payload(i) == content(i) per index ---


def test_distinct_content_probe_preview_identity_per_side(monkeypatch, tmp_path):
    """N distinguishable previews: each side resolves its own content.

    Counts/sizes alone are rejected as correctness — every side asserts
    its exact pixel color.
    """
    import shared.image_processing.progressive_loader as pl

    colors = [(200, 30, 30), (30, 200, 30), (30, 30, 200), (200, 200, 30)]
    files = [_write_file(tmp_path / f"side{i}.png", bytes([i]) * 8) for i in range(4)]
    palette = {str(p): _color_image(*c) for p, c in zip(files, colors)}
    monkeypatch.setattr(pl, "load_preview_image", lambda path: palette[str(path)])
    cache = _FakeCache()
    for i, path in enumerate(files):
        got = get_or_load_preview(cache, path)
        want = QColor(*colors[i])
        assert got.pixelColor(0, 0) == want, f"side {i}: payload must equal content({i})"
    assert len(cache.previews) == 4


def test_distinct_content_probe_pixel_identity_per_side(monkeypatch, tmp_path):
    import shared.image_processing.pixel_cache_loader as pcl

    files = [_write_file(tmp_path / f"full{i}.png", bytes([i + 1]) * 8) for i in range(3)]
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
    cache.put_preview(str(tmp_path / "shown.png"), _color_image(9, 9, 9))
    assert get_or_load_preview(cache, tmp_path / "empty.png") is None


def test_evicted_slot_returns_to_gap(monkeypatch, tmp_path):
    import shared.image_processing.progressive_loader as pl

    f = _write_file(tmp_path / "a.png", b"evict-me")
    img = _color_image(1, 2, 3)
    monkeypatch.setattr(pl, "load_preview_image", lambda path: img)
    cache = _FakeCache()
    assert get_or_load_preview(cache, f) is img
    cache.previews.clear()  # eviction
    monkeypatch.setattr(pl, "load_preview_image", lambda path: None)
    assert get_or_load_preview(cache, f) is None, "evicted slot reads as gap"


def test_stale_after_fresh_key_diverges_and_fresh_wins(monkeypatch, tmp_path):
    import shared.image_processing.progressive_loader as pl

    f = _write_file(tmp_path / "a.png", b"fresh-v1!!")
    stale_key = cache_key_for_path(f)
    f.write_bytes(b"fresh-v2!!-changed-length")
    fresh_key = cache_key_for_path(f)
    assert stale_key != fresh_key
    fresh_img = _color_image(77, 88, 99)
    monkeypatch.setattr(pl, "load_preview_image", lambda path: fresh_img)
    cache = _FakeCache()
    assert get_or_load_preview(cache, f) is fresh_img


# --- index in cache keys: divider sides route to their own slot ---


def test_ensure_async_delivers_per_side_ids_with_own_payloads(monkeypatch, tmp_path):
    """Divider sides 0/1: same-file fans out to both ids, distinct files
    never cross (slot id is part of the async routing key)."""
    import shared.image_processing.pixel_cache_loader as pcl
    import shared.image_processing.progressive_loader as pl

    left = _write_file(tmp_path / "left.png", b"left Payload")
    right = _write_file(tmp_path / "right.png", b"right-PAYLOAD")
    previews = {
        str(left): _color_image(210, 40, 40),
        str(right): _color_image(40, 40, 210),
    }
    fulls = {str(left): _FakeStore("left-full"), str(right): _FakeStore("right-full")}
    monkeypatch.setattr(pl, "load_preview_image", lambda path: previews[str(path)])
    monkeypatch.setattr(pcl, "load_pixel_store", lambda path, **kw: fulls.get(str(path)))

    cache = _FakeCache()
    seen: list[tuple] = []
    ensure_async(cache, left, 0, on_ready=lambda sid, p, obj: seen.append((sid, str(p), obj)))
    ensure_async(cache, right, 1, on_ready=lambda sid, p, obj: seen.append((sid, str(p), obj)))
    by_slot = {sid: (p, obj) for sid, p, obj in seen}
    assert set(by_slot) == {0, 1}, "both divider sides delivered"
    assert by_slot[0][0] == str(left) and by_slot[1][0] == str(right)
    for sid, (_, obj) in by_slot.items():
        assert obj is previews[by_slot[sid][0]] or obj is fulls[by_slot[sid][0]]
    # No cross: side 0 never saw the right payload and vice versa.
    assert all(obj is not previews[str(right)] for sid, _, obj in seen if sid == 0)
    assert all(obj is not previews[str(left)] for sid, _, obj in seen if sid == 1)


def test_ensure_async_same_file_fans_out_to_both_sides(monkeypatch, tmp_path):
    import shared.image_processing.pixel_cache_loader as pcl
    import shared.image_processing.progressive_loader as pl

    f = _write_file(tmp_path / "same.png", b"same")
    img = _color_image(5, 6, 7)
    monkeypatch.setattr(pl, "load_preview_image", lambda path: img)
    monkeypatch.setattr(pcl, "load_pixel_store", lambda path, **kw: _FakeStore("same-full"))
    cache = _FakeCache()
    seen: list[tuple] = []
    ensure_async(cache, f, 0, on_ready=lambda sid, p, obj: seen.append((sid, obj)))
    ensure_async(cache, f, 1, on_ready=lambda sid, p, obj: seen.append((sid, obj)))
    assert {sid for sid, _ in seen} == {0, 1}
    assert all(obj is img or getattr(obj, "tag", None) == "same-full" for _, obj in seen)


def test_ensure_async_miss_calls_on_error_never_neighbor(monkeypatch, tmp_path):
    import shared.image_processing.pixel_cache_loader as pcl
    import shared.image_processing.progressive_loader as pl

    good = _write_file(tmp_path / "good.png", b"good")
    bad = tmp_path / "bad.png"
    neighbor = _color_image(200, 10, 10)
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
        1,
        on_ready=lambda sid, p, obj: ready.append((sid, obj)),
        on_error=lambda sid, p, err: errors.append((sid, err)),
    )
    assert ready == [], "miss must never deliver — not even the neighbor tier"
    assert [sid for sid, _ in errors] == [1]


def test_full_queue_entries_carry_slot_id(monkeypatch):
    """Queued full-res work is keyed by slot id (index in the key)."""
    started: list = []

    class _StubPool:
        def start(self, worker):
            started.append(worker)

    monkeypatch.setattr(seam, "_global_thread_pool", lambda: _StubPool())
    queue_full_resolution("a.png", 0)
    queue_full_resolution("b.png", 1)
    try:
        assert set(seam._full_active) == {0, 1}, "full stage keyed by slot id"
        assert seam._full_active[0]["path"] == "a.png"
        assert seam._full_active[1]["path"] == "b.png"
        assert len(started) == 2
    finally:
        seam._full_active.clear()
        seam._full_queue.clear()


# --- picking + pyramid hook: fail-open, usable tiers first ---


def test_pick_display_image_prefers_first_real_and_gaps_to_none():
    preview = _color_image(11, 22, 33)
    assert pick_display_image(None, preview) is preview
    assert pick_display_image(None, None) is None
    assert pick_display_image() is None


def test_start_pyramid_build_fail_open():
    start_pyramid_build(None, 0, None)
    start_pyramid_build(_FakeStore("x"), 0, None)

    def _boom(store, slot_id):
        raise RuntimeError("toast exploded")

    start_pyramid_build(_FakeStore("x"), 0, _boom)  # must not raise
