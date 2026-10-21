from __future__ import annotations

from pathlib import Path

from tabs.image_gallery.models import AiAnalysisResult
from tabs.image_gallery.services import ai_cache

#: The analysis identity these mechanics tests cache under. Real callers derive
#: it from ``AiSettings`` + the call context (``analysis_cache_identity``); the
#: per-backend miss semantics live in ``test_ai_cache_identity.py``.
IDENTITY = ai_cache.analysis_cache_identity(
    None, mode="camera", profile=("sharpness", "noise")
)
OTHER_IDENTITY = ai_cache.analysis_cache_identity(
    None, mode="fidelity", profile=("sharpness", "noise")
)


def test_save_and_load_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(ai_cache, "ai_cache_dir", lambda: tmp_path)
    path = Path("/some/image.png")
    result = AiAnalysisResult(
        description="A test image.",
        tags=("a", "b"),
        model="test/model",
        analyzed_at_iso="2026-01-01T00:00:00+00:00",
    )

    ai_cache.save_analysis(path, 123, result, IDENTITY)
    loaded = ai_cache.load_cached_analysis(path, 123, IDENTITY)

    assert loaded == result


def test_load_returns_none_when_uncached(tmp_path, monkeypatch):
    monkeypatch.setattr(ai_cache, "ai_cache_dir", lambda: tmp_path)
    assert ai_cache.load_cached_analysis(Path("/nope.png"), 1, IDENTITY) is None


def test_round_trip_carries_quality_and_reason(tmp_path, monkeypatch):
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
        reason="Clean.",
        axis_notes={"noise": "coarse film grain"},
        axes={"sharpness": 85, "noise": 90, "exposure": 78, "composition": 80, "ssim": 72},
    )
    ai_cache.save_analysis(path, 123, result, IDENTITY)
    assert ai_cache.load_cached_analysis(path, 123, IDENTITY) == result
    stored = json.loads(next(tmp_path.iterdir()).read_text(encoding="utf-8"))
    assert stored["sharpness"] == 85
    assert stored["reason"] == "Clean."
    assert stored["axis_notes"] == {"noise": "coarse film grain"}
    assert stored["axes"]["ssim"] == 72
    assert stored["version"] == ai_cache.AI_CACHE_VERSION
    assert stored["identity"] == IDENTITY


def test_pre_scorecard_cache_is_a_miss_not_an_ai_read(tmp_path, monkeypatch):
    """A v1 (pre-scorecard) entry is a MISS: its named scores are detector
    values (old ``_merge_measured_metrics``) — never served as the AI read, so
    the AI domain re-analyzes it (plan-gallery-ai-backend-owns-quality)."""
    import json

    monkeypatch.setattr(ai_cache, "ai_cache_dir", lambda: tmp_path)
    path = Path("/some/image.png")
    ai_cache.save_analysis(
        path,
        123,
        AiAnalysisResult(
            description="d", tags=(), model="m",
            analyzed_at_iso="2026-01-01T00:00:00+00:00",
            sharpness=64, composition=58, reason="stale",
        ),
        IDENTITY,
    )
    cache_file = next(tmp_path.iterdir())
    data = json.loads(cache_file.read_text(encoding="utf-8"))
    data.pop("version", None)  # simulate a pre-scorecard (v1) entry
    data.pop("axes", None)
    cache_file.write_text(json.dumps(data), encoding="utf-8")

    assert ai_cache.load_cached_analysis(path, 123, IDENTITY) is None


def test_current_entry_without_numeric_axes_loads_unscored(tmp_path, monkeypatch):
    """A current entry that carries no scores (all -1) still loads, unscored."""
    import json

    monkeypatch.setattr(ai_cache, "ai_cache_dir", lambda: tmp_path)
    path = Path("/some/image.png")
    ai_cache.save_analysis(
        path,
        123,
        AiAnalysisResult(
            description="old caption",
            tags=("a",),
            model="m",
            analyzed_at_iso="2026-01-01T00:00:00+00:00",
        ),
        IDENTITY,
    )
    cache_file = next(tmp_path.iterdir())
    data = json.loads(cache_file.read_text(encoding="utf-8"))
    for key in ("sharpness", "noise", "exposure", "composition", "reason"):
        data.pop(key, None)
    cache_file.write_text(json.dumps(data), encoding="utf-8")
    loaded = ai_cache.load_cached_analysis(path, 123, IDENTITY)
    assert loaded is not None
    assert loaded.description == "old caption"
    assert (loaded.sharpness, loaded.noise, loaded.exposure, loaded.composition) == (-1, -1, -1, -1)
    assert loaded.reason == ""
    assert not hasattr(loaded, "verdict")


def test_key_changes_with_mtime_treats_edited_file_as_uncached(tmp_path, monkeypatch):
    monkeypatch.setattr(ai_cache, "ai_cache_dir", lambda: tmp_path)
    path = Path("/some/image.png")
    result = AiAnalysisResult(
        description="desc", tags=(), model="m", analyzed_at_iso="2026-01-01T00:00:00+00:00"
    )
    ai_cache.save_analysis(path, 100, result, IDENTITY)

    assert ai_cache.load_cached_analysis(path, 100, IDENTITY) == result
    assert ai_cache.load_cached_analysis(path, 200, IDENTITY) is None


def test_key_changes_with_the_identity_treats_it_as_uncached(tmp_path, monkeypatch):
    """Same image, same mtime, different analysis configuration: separate entries."""
    monkeypatch.setattr(ai_cache, "ai_cache_dir", lambda: tmp_path)
    path = Path("/some/image.png")
    result = AiAnalysisResult(
        description="desc", tags=(), model="m", analyzed_at_iso="2026-01-01T00:00:00+00:00"
    )
    ai_cache.save_analysis(path, 100, result, IDENTITY)

    assert ai_cache.load_cached_analysis(path, 100, OTHER_IDENTITY) is None
    # Both variants coexist: switching back does not overwrite the other read.
    other = AiAnalysisResult(
        description="other", tags=(), model="m", analyzed_at_iso="2026-01-01T00:00:00+00:00"
    )
    ai_cache.save_analysis(path, 100, other, OTHER_IDENTITY)
    assert ai_cache.load_cached_analysis(path, 100, IDENTITY) == result
    assert ai_cache.load_cached_analysis(path, 100, OTHER_IDENTITY) == other
