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