"""thumbnail_cache disk roundtrip: render->disk, hit, and corrupt recovery.

Mirrors ``test_ai_cache_roundtrip.py``: the cache dir is monkeypatched to a
``tmp_path`` so no real user cache dir is ever touched. Covers the three
behaviors the key-only tests (``test_thumbnail_cache_key.py``) cannot:
1. ``render_and_cache_thumbnail`` writes a real PNG to disk;
2. a cache hit returns the cached file without re-rendering;
3. a corrupt cache entry (garbage bytes) is not returned as a hit — it is
   dropped and re-rendered, never crashing.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from tabs.image_gallery.services import thumbnail_cache

_SOURCE_SIZE = (640, 480)


def _redirect_cache(tmp_path, monkeypatch) -> Path:
    cache_dir = tmp_path / "cache"

    def _dir() -> Path:
        # The real thumbnail_cache_dir() mkdirs; keep that contract.
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir

    monkeypatch.setattr(thumbnail_cache, "thumbnail_cache_dir", _dir)
    return cache_dir


def _make_source_image(tmp_path, name: str = "source.png") -> Path:
    image = Image.new("RGB", _SOURCE_SIZE, (200, 100, 50))
    path = tmp_path / name
    image.save(path, "PNG")
    return path


def test_render_and_cache_thumbnail_writes_file_to_disk(tmp_path, monkeypatch):
    """First render lands a valid, bounded PNG in the cache dir."""
    _redirect_cache(tmp_path, monkeypatch)
    source = _make_source_image(tmp_path)

    result = thumbnail_cache.render_and_cache_thumbnail(source, 123)

    expected = thumbnail_cache.cached_thumbnail_path(source, 123)
    assert result == expected
    assert expected.is_file()
    with Image.open(expected) as cached:
        width, height = cached.size
        # Content identity: the cached thumbnail is the SOURCE's image, not
        # another file's (a bounded-size-only check would pass on a collision).
        center = cached.convert("RGB").getpixel((width // 2, height // 2))
    assert width <= thumbnail_cache.THUMBNAIL_SIZE[0]
    assert height <= thumbnail_cache.THUMBNAIL_SIZE[1]
    assert center == (200, 100, 50)


def test_cache_hit_returns_cached_file_without_rerender(tmp_path, monkeypatch):
    """A valid cache entry is returned as-is on the next call."""
    _redirect_cache(tmp_path, monkeypatch)
    source = _make_source_image(tmp_path)
    first = thumbnail_cache.render_and_cache_thumbnail(source, 123)
    cached_path = thumbnail_cache.cached_thumbnail_path(source, 123)
    mtime_before = cached_path.stat().st_mtime_ns

    second = thumbnail_cache.render_and_cache_thumbnail(source, 123)

    assert first == second == cached_path
    assert cached_path.stat().st_mtime_ns == mtime_before, (
        "a cache hit must not re-render the cached file"
    )


def test_corrupt_cache_file_is_recovered_by_rerender(tmp_path, monkeypatch):
    """Garbage bytes in the cache file must not be a hit and must not crash.

    The corrupt entry is replaced by a freshly rendered thumbnail, so the
    next open of the folder heals the cache instead of showing a
    permanently broken thumbnail.
    """
    _redirect_cache(tmp_path, monkeypatch)
    source = _make_source_image(tmp_path)
    cached_path = thumbnail_cache.cached_thumbnail_path(source, 123)
    cached_path.parent.mkdir(parents=True, exist_ok=True)
    cached_path.write_bytes(b"\x89PNG not-a-real-png-any-more")

    result = thumbnail_cache.render_and_cache_thumbnail(source, 123)

    assert result == cached_path
    with Image.open(cached_path) as healed:
        healed.verify()  # now a real PNG again (raises on the garbage bytes)


def test_render_failure_is_a_graceful_miss(tmp_path, monkeypatch):
    """An unrenderable source yields ``None`` and no cache file."""
    _redirect_cache(tmp_path, monkeypatch)
    broken = tmp_path / "broken.png"
    broken.write_bytes(b"definitely not an image")

    assert thumbnail_cache.render_and_cache_thumbnail(broken, 123) is None
    assert not thumbnail_cache.cached_thumbnail_path(broken, 123).exists()
