from __future__ import annotations

from pathlib import Path

from tabs.image_gallery.models import AiAnalysisResult
from tabs.image_gallery.services import ai_cache


def test_save_and_load_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(ai_cache, "ai_cache_dir", lambda: tmp_path)
    path = Path("/some/image.png")
    result = AiAnalysisResult(
        description="A test image.",
        tags=("a", "b"),
        model="test/model",
        analyzed_at_iso="2026-01-01T00:00:00+00:00",
    )

    ai_cache.save_analysis(path, 123, result)
    loaded = ai_cache.load_cached_analysis(path, 123)

    assert loaded == result


def test_load_returns_none_when_uncached(tmp_path, monkeypatch):
    monkeypatch.setattr(ai_cache, "ai_cache_dir", lambda: tmp_path)
    assert ai_cache.load_cached_analysis(Path("/nope.png"), 1) is None


def test_key_changes_with_mtime_treats_edited_file_as_uncached(tmp_path, monkeypatch):
    monkeypatch.setattr(ai_cache, "ai_cache_dir", lambda: tmp_path)
    path = Path("/some/image.png")
    result = AiAnalysisResult(
        description="desc", tags=(), model="m", analyzed_at_iso="2026-01-01T00:00:00+00:00"
    )
    ai_cache.save_analysis(path, 100, result)

    assert ai_cache.load_cached_analysis(path, 100) == result
    assert ai_cache.load_cached_analysis(path, 200) is None