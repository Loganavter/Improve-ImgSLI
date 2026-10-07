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


def test_round_trip_carries_quality_and_verdict(tmp_path, monkeypatch):
    import json

    monkeypatch.setattr(ai_cache, "ai_cache_dir", lambda: tmp_path)
    path = Path("/some/image.png")
    result = AiAnalysisResult(
        description="d",
        tags=("a",),
        model="m",
        analyzed_at_iso="2026-01-01T00:00:00+00:00",
        sharpness=85,
        noise=90,
        exposure=78,
        composition=80,
        verdict="keep",
        verdict_reason="Clean.",
    )
    ai_cache.save_analysis(path, 123, result)
    assert ai_cache.load_cached_analysis(path, 123) == result
    stored = json.loads(next(tmp_path.iterdir()).read_text(encoding="utf-8"))
    assert stored["sharpness"] == 85
    assert stored["verdict"] == "keep"


def test_legacy_caption_only_cache_loads_as_unscored(tmp_path, monkeypatch):
    import json

    monkeypatch.setattr(ai_cache, "ai_cache_dir", lambda: tmp_path)
    path = Path("/some/image.png")
    # Cache filename is hash-based: save through the writer, then strip the
    # new keys to simulate a legacy entry.
    ai_cache.save_analysis(
        path,
        123,
        AiAnalysisResult(
            description="old caption",
            tags=("a",),
            model="m",
            analyzed_at_iso="2026-01-01T00:00:00+00:00",
        ),
    )
    cache_file = next(tmp_path.iterdir())
    data = json.loads(cache_file.read_text(encoding="utf-8"))
    for key in ("sharpness", "noise", "exposure", "composition", "verdict", "verdict_reason"):
        data.pop(key, None)
    cache_file.write_text(json.dumps(data), encoding="utf-8")
    loaded = ai_cache.load_cached_analysis(path, 123)
    assert loaded is not None
    assert loaded.description == "old caption"
    assert (loaded.sharpness, loaded.noise, loaded.exposure, loaded.composition) == (-1, -1, -1, -1)
    assert loaded.verdict == "unknown"


def test_key_changes_with_mtime_treats_edited_file_as_uncached(tmp_path, monkeypatch):
    monkeypatch.setattr(ai_cache, "ai_cache_dir", lambda: tmp_path)
    path = Path("/some/image.png")
    result = AiAnalysisResult(
        description="desc", tags=(), model="m", analyzed_at_iso="2026-01-01T00:00:00+00:00"
    )
    ai_cache.save_analysis(path, 100, result)

    assert ai_cache.load_cached_analysis(path, 100) == result
    assert ai_cache.load_cached_analysis(path, 200) is None