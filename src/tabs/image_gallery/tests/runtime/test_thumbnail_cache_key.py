from __future__ import annotations

from pathlib import Path

from tabs.image_gallery.services.thumbnail_cache import cache_key_for


def test_cache_key_stable_for_same_path_and_mtime():
    path = Path("/some/image.png")
    assert cache_key_for(path, 123) == cache_key_for(path, 123)


def test_cache_key_changes_with_mtime():
    path = Path("/some/image.png")
    assert cache_key_for(path, 123) != cache_key_for(path, 456)


def test_cache_key_changes_with_path():
    assert cache_key_for(Path("/a.png"), 1) != cache_key_for(Path("/b.png"), 1)

def test_cache_key_accepts_an_explicit_content_identity():
    """The keyword form skips the read: the caller already has the digest."""
    path = Path("/some/image.png")
    assert cache_key_for(path, 123, digest="a" * 32) != cache_key_for(
        path, 123, digest="b" * 32
    )
    # Same bytes under another name / mtime is one key — the copy is a HIT.
    assert cache_key_for(Path("/a.png"), 1, digest="c" * 32) == cache_key_for(
        Path("/b.png"), 999, digest="c" * 32
    )
    # An unreadable file keeps the path-keyed form and its size filter.
    assert cache_key_for(path, 123, size=10) == cache_key_for(path, 123, size=10)
    assert cache_key_for(path, 123, size=10) != cache_key_for(path, 123, size=11)
