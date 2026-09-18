"""P2 persistent thumbnail disk cache — structure contracts, no timing asserts.

Proves: cold run populates the cache dir; warm run emits via the existing
``_on_thumbnail_generated`` path with zero worker starts (fake renderer
call-count == 0); changed autocrop/split poisons the key (miss); LRU
evicts oldest-first under count + byte caps; corrupt entries are a miss;
stale-generation completions never populate the cache.

Dogma source: THUMB_PLAN.md (P2) — hash conservatively, prefer a miss over
a wrong hit; timing assertions live only in logs/manual runs, never here.
"""

from __future__ import annotations

import logging
import os
from types import SimpleNamespace

from PIL import Image

_THUMB = (160, 90)


def _write_source(path, color=(200, 100, 50)):
    Image.new("RGB", (64, 36), color).save(str(path), "PNG")
    return str(path)


def _snap(*, path1, path2, timestamp=0.0, split=0.5, frame=0):
    return SimpleNamespace(
        timestamp=timestamp,
        image1_path=path1,
        image2_path=path2,
        name1="a",
        name2="b",
        viewport_state={"frame": frame, "split": split},
        settings_state={"mode": "compare"},
    )


class _Recording:
    """Duck-typed recording: ``evaluate_at`` maps ts back to per-index snaps."""

    def __init__(self, snaps, duration=10.0, fps=60):
        self._snaps = list(snaps)
        self._duration = duration
        self._fps = fps

    def evaluate_at(self, timestamp: float):
        idx = min(max(0, int(round(float(timestamp) * self._fps))), len(self._snaps) - 1)
        return self._snaps[idx]

    def get_duration(self) -> float:
        return self._duration


def _harness(monkeypatch, tmp_path, *, split=0.5, auto_crop=False,
             fresh_sources=True):
    from tabs.image_compare.plugins.video_editor.services.thumbnail_cache import (
        ThumbnailDiskCache,
    )
    from tabs.image_compare.plugins.video_editor.services.thumbnails import (
        ThumbnailService,
    )

    img1_path, img2_path = tmp_path / "img1.png", tmp_path / "img2.png"
    if fresh_sources or not img1_path.exists():
        _write_source(img1_path, (200, 100, 50))
    if fresh_sources or not img2_path.exists():
        _write_source(img2_path, (50, 100, 200))
    src1, src2 = str(img1_path), str(img2_path)
    snaps = [
        _snap(path1=src1, path2=src2, timestamp=i / 60.0, split=split, frame=i)
        for i in range(3)
    ]
    cache = ThumbnailDiskCache(cache_dir=str(tmp_path / "thumbcache"))
    service = ThumbnailService()
    service.set_thumbnail_disk_cache(cache)
    # Synchronous pool: workers run inline, signals emit inline.
    monkeypatch.setattr(
        service._thread_pool, "start", lambda worker, priority=0: worker.run()
    )
    calls: list[tuple] = []

    def fake_render(snap, w, h, *, auto_crop=False):
        calls.append((w, h, auto_crop))
        return Image.new("RGBA", _THUMB, (50, 100, 150, 255))

    service.set_snapshot_renderer(fake_render)
    emitted: dict[int, object] = {}
    service.thumbnailReady.connect(lambda i, px: emitted.__setitem__(i, px))
    finished: list[int] = []
    service.generationFinished.connect(lambda: finished.append(1))
    recording = _Recording(snaps)
    return SimpleNamespace(
        service=service,
        cache=cache,
        calls=calls,
        emitted=emitted,
        finished=finished,
        recording=recording,
        auto_crop=auto_crop,
    )


def _generate(harness):
    return harness.service.generate_thumbnails(
        harness.recording,
        target_count=50,
        thumbnail_size=_THUMB,
        auto_crop=harness.auto_crop,
        priority_indices=[0, 1, 2],
        fps=60,
    )


def _cache_files(harness):
    return sorted(
        p
        for p in os.listdir(harness.cache.cache_dir)
        if p.endswith(".png") and not p.startswith(".")
    )


def test_cold_run_populates_cache_dir(qapp, monkeypatch, tmp_path):
    h = _harness(monkeypatch, tmp_path)
    _generate(h)

    assert len(h.calls) == 3, "cold run must render every thumbnail"
    assert sorted(h.emitted) == [0, 1, 2]
    assert all(not px.isNull() for px in h.emitted.values())
    assert h.finished == [1]
    assert len(_cache_files(h)) == 3, "cold run must store one PNG per thumbnail"


def test_warm_run_emits_without_workers(qapp, monkeypatch, tmp_path, caplog):
    h = _harness(monkeypatch, tmp_path)
    _generate(h)
    assert len(_cache_files(h)) == 3

    h2 = _harness(monkeypatch, tmp_path, fresh_sources=False)
    # Same sources + params, same cache dir → every index is a hit.
    h2.cache = h.cache
    h2.service.set_thumbnail_disk_cache(h.cache)
    with caplog.at_level(logging.DEBUG, logger="ImproveImgSLI.video_thumbnails"):
        _generate(h2)

    assert h2.calls == [], "warm run must not call the renderer"
    assert "thumbnail_worker_start" not in caplog.text
    assert sorted(h2.emitted) == [0, 1, 2]
    assert all(not px.isNull() for px in h2.emitted.values())
    assert h2.finished == [1], "cache-hit wave must still finish the generation"


def test_changed_autocrop_misses(qapp, monkeypatch, tmp_path):
    h = _harness(monkeypatch, tmp_path, auto_crop=False)
    _generate(h)
    assert len(_cache_files(h)) == 3

    h2 = _harness(monkeypatch, tmp_path, auto_crop=True, fresh_sources=False)
    h2.cache = h.cache
    h2.service.set_thumbnail_disk_cache(h.cache)
    _generate(h2)

    assert len(h2.calls) == 3, "flipped autocrop must poison every key"
    assert sorted(h2.emitted) == [0, 1, 2]


def test_changed_split_misses(qapp, monkeypatch, tmp_path):
    h = _harness(monkeypatch, tmp_path, split=0.5)
    _generate(h)

    h2 = _harness(monkeypatch, tmp_path, split=0.9, fresh_sources=False)
    h2.cache = h.cache
    h2.service.set_thumbnail_disk_cache(h.cache)
    _generate(h2)

    assert len(h2.calls) == 3, "moved split must poison every key"


def test_stale_generation_completion_never_populates_cache(
    qapp, monkeypatch, tmp_path
):
    h = _harness(monkeypatch, tmp_path)
    assert _cache_files(h) == []

    stale_gen = h.service._generation + 100
    h.service._on_thumbnail_generated(
        7, Image.new("RGBA", _THUMB, (1, 2, 3, 255)), stale_gen
    )

    assert _cache_files(h) == [], "stale completion must not write to the cache"
    assert 7 not in h.service._generated_indices
    assert h.emitted == {}


def test_key_builder_hashes_conservatively(tmp_path):
    from tabs.image_compare.plugins.video_editor.services.thumbnail_cache import (
        thumbnail_cache_key_for_snap,
    )

    src1 = _write_source(tmp_path / "a.png")
    src2 = _write_source(tmp_path / "b.png")

    def key(**over):
        params = dict(
            path1=src1, path2=src2, timestamp=1.0, split=0.5, frame=3
        )
        params.update(over)
        return thumbnail_cache_key_for_snap(
            _snap(**params), auto_crop=False, thumbnail_size=_THUMB
        )

    base = key()
    assert base is not None
    assert key() == base, "same inputs must key identically"
    assert key(split=0.9) != base, "split must be in the key"
    assert key(frame=4) != base, "frame identity must be in the key"
    assert (
        thumbnail_cache_key_for_snap(
            _snap(path1=src1, path2=src2), auto_crop=True, thumbnail_size=_THUMB
        )
        != base
    ), "autocrop flag must be in the key"
    assert key(path1=str(tmp_path / "missing.png")) is None, (
        "unstatable source is doubt → miss, never a guess"
    )
    assert (
        thumbnail_cache_key_for_snap(
            _snap(path1=src1, path2=src2), auto_crop=False, thumbnail_size=(0, 0)
        )
        is None
    )

    # Source bytes change (same path) → miss.
    _write_source(tmp_path / "a.png", (1, 2, 3))
    assert key() != base

    # Unhashable snapshot state → miss, never a guess.
    class _BadRepr:
        def __repr__(self):
            raise ValueError("unreprable")

    bad = _snap(path1=src1, path2=src2)
    bad.viewport_state = _BadRepr()
    assert (
        thumbnail_cache_key_for_snap(bad, auto_crop=False, thumbnail_size=_THUMB)
        is None
    )


def test_lru_evicts_oldest_first(tmp_path):
    from tabs.image_compare.plugins.video_editor.services.thumbnail_cache import (
        ThumbnailDiskCache,
        thumbnail_cache_key_for_snap,
    )

    cache = ThumbnailDiskCache(cache_dir=str(tmp_path / "lru"), max_entries=3)
    src1 = _write_source(tmp_path / "a.png")
    src2 = _write_source(tmp_path / "b.png")
    keys = [
        thumbnail_cache_key_for_snap(
            _snap(path1=src1, path2=src2, frame=i),
            auto_crop=False,
            thumbnail_size=_THUMB,
        )
        for i in range(4)
    ]
    assert all(k is not None for k in keys)
    base_ts = 1_700_000_000
    for n, k in enumerate(keys[:3]):
        assert cache.put(k, Image.new("RGBA", _THUMB, (n, 0, 0, 255)))
        os.utime(cache._path_for_key(k), (base_ts + n, base_ts + n))
    assert cache.put(keys[3], Image.new("RGBA", _THUMB, (9, 9, 9, 255)))

    assert cache.get(keys[0], expected_size=_THUMB) is None, "oldest must be evicted"
    assert not os.path.exists(cache._path_for_key(keys[0]))
    for k in keys[1:]:
        hit = cache.get(k, expected_size=_THUMB)
        assert hit is not None and hit.size == _THUMB


def test_byte_cap_evicts(tmp_path):
    from tabs.image_compare.plugins.video_editor.services.thumbnail_cache import (
        ThumbnailDiskCache,
    )

    cache = ThumbnailDiskCache(cache_dir=str(tmp_path / "bytes"), max_bytes=1)
    import hashlib as _hl

    assert cache.put(_hl.sha256(b"one").hexdigest(), Image.new("RGBA", _THUMB))
    assert cache.put(_hl.sha256(b"two").hexdigest(), Image.new("RGBA", _THUMB))
    leftovers = [
        p for p in os.listdir(cache.cache_dir) if p.endswith(".png")
    ]
    assert leftovers == [], "byte cap must evict everything over budget"


def test_corrupt_entry_is_miss_then_overwritten(tmp_path):
    from tabs.image_compare.plugins.video_editor.services.thumbnail_cache import (
        ThumbnailDiskCache,
    )

    import hashlib as _hl

    cache = ThumbnailDiskCache(cache_dir=str(tmp_path / "corrupt"))
    key = _hl.sha256(b"thumb").hexdigest()
    assert cache.put(key, Image.new("RGBA", _THUMB, (10, 20, 30, 255)))
    assert cache.get(key, expected_size=_THUMB) is not None

    with open(cache._path_for_key(key), "wb") as handle:
        handle.write(b"\x00\x01 definitely not a png")
    assert cache.get(key, expected_size=_THUMB) is None, "corrupt bytes are a miss"

    assert cache.put(key, Image.new("RGBA", _THUMB, (10, 20, 30, 255)))
    hit = cache.get(key, expected_size=_THUMB)
    assert hit is not None and hit.size == _THUMB, "next store overwrites"

    wrong_size_key = _hl.sha256(b"wrong-size").hexdigest()
    assert cache.put(wrong_size_key, Image.new("RGBA", (32, 32), (1, 1, 1, 255)))
    assert cache.get(wrong_size_key, expected_size=_THUMB) is None


def test_cache_dir_is_thumbnail_subdir_not_log_dir(tmp_path, monkeypatch):
    import tabs.image_compare.plugins.video_editor.services.thumbnail_cache as mod

    monkeypatch.setattr(
        "sli_ui_toolkit.core.logging.get_log_directory",
        lambda _app: str(tmp_path / "LOGDIR"),
    )
    assert mod.default_thumbnail_cache_dir() == str(tmp_path / "LOGDIR" / "thumbnails")

    cache = mod.ThumbnailDiskCache()
    assert cache.cache_dir == str(tmp_path / "LOGDIR" / "thumbnails")
    assert os.path.isdir(cache.cache_dir)
