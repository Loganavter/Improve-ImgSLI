"""The AI disk cache must be keyed by the ANALYSIS configuration, not just the file.

The bug (queue id ``task-gallery-ai-cache-backend-key-2026-10-20``):
``services/ai_cache.py`` keyed entries on ``cache_key_for(path, mtime_ns)`` only,
so after switching model / base_url / mode / profile / reasoning effort,
``use_cases/ai_analysis.analyze_item`` served the PREVIOUS backend's scorecard
from disk before it had even read ``AiSettings``.

The contract asserted here:

* one identity helper (``analysis_cache_identity``) derived from ``AiSettings`` +
  the call context, covering model, base_url, mode, active profile's axes,
  reasoning effort and the prompt/schema version;
* a different identity is a MISS (and the same identity still HITs);
* the identity is stored in the payload and validated on load (defence in depth);
* a pre-identity entry is a miss, without a migration attempt or a crash;
* ``api_key`` never reaches the key or the JSON payload.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from tabs.image_gallery.models import AiAnalysisResult
from tabs.image_gallery.services import ai_cache
from tabs.image_gallery.services.ai_settings_store import AiSettings
from tabs.image_gallery.services.thumbnail_cache import cache_key_for

PROFILE = ("sharpness", "noise", "exposure", "composition")


def _settings(**overrides) -> AiSettings:
    base = dict(
        enabled=True,
        base_url="https://openrouter.ai/api/v1",
        api_key="sk-secret-value",
        model="model/A",
        reasoning_effort="auto",
    )
    base.update(overrides)
    return AiSettings(**base)


def _identity(settings=None, **ctx) -> dict:
    """The identity for ``settings`` with the given call context overrides."""
    settings = settings if settings is not None else _settings()
    kwargs = dict(mode="camera", profile=PROFILE, reasoning_effort=None)
    kwargs.update(ctx)
    return ai_cache.analysis_cache_identity(settings, **kwargs)


def _result(description: str = "from A", model: str = "model/A") -> AiAnalysisResult:
    return AiAnalysisResult(
        description=description,
        tags=("sky",),
        model=model,
        analyzed_at_iso="2026-01-01T00:00:00+00:00",
        sharpness=80,
        composition=70,
        verdict="keep",
    )


def _cache_dir(tmp_path, monkeypatch) -> Path:
    cache = tmp_path / "ai_cache"
    cache.mkdir()
    monkeypatch.setattr(ai_cache, "ai_cache_dir", lambda: cache)
    return cache


# ---------------------------------------------------------------------------
# the user-visible bug: analyze_item served backend A's scorecard to backend B
# ---------------------------------------------------------------------------


def _owner(settings, started: list) -> SimpleNamespace:
    """A minimal analyze-path owner: settings, mode, card refresh, begin seam."""
    return SimpleNamespace(
        state=SimpleNamespace(mode="camera", metric_profile=None, items=[]),
        widget=SimpleNamespace(refresh_card=lambda it: None),
        _ai_settings_store=SimpleNamespace(load=lambda: settings),
        _begin_analysis=lambda it: started.append(it),
    )


def test_analyze_item_does_not_serve_another_models_scorecard(tmp_path, monkeypatch) -> None:
    """A cached A scorecard must NOT short-circuit an analysis configured for B."""
    from tabs.image_gallery.use_cases import ai_analysis

    _cache_dir(tmp_path, monkeypatch)
    path = Path("/gallery/frame.png")
    # Cache a real model-A read under model A's identity.
    ai_cache.save_analysis(
        path, 42, _result(), ai_analysis.analysis_identity_for(_owner(_settings(), []))
    )

    started: list = []
    owner_b = _owner(_settings(model="model/B"), started)
    item = SimpleNamespace(path=path, mtime_ns=42, analysis=None)

    ai_analysis.analyze_item(owner_b, item)

    assert item.analysis is None, "backend B was served backend A's cached scorecard"
    assert len(started) == 1, "a different backend must start a real analysis"


def _write_legacy_entry(cache: Path, path: Path, mtime: int, *, description: str) -> Path:
    """An entry as the PRE-FIX cache wrote it: ``<path:mtime>.json``, no identity."""
    legacy = cache / f"{cache_key_for(path, mtime)}.json"
    legacy.write_text(
        json.dumps(
            {
                "description": description,
                "tags": ["sky"],
                "model": "model/A",
                "analyzed_at_iso": "2026-01-01T00:00:00+00:00",
                "sharpness": 80,
                "composition": 70,
                "verdict": "keep",
                "axes": {"sharpness": 80, "composition": 70},
                "version": ai_cache.AI_CACHE_VERSION,
            }
        ),
        encoding="utf-8",
    )
    return legacy


def test_analyze_item_never_serves_a_pre_identity_entry(tmp_path, monkeypatch) -> None:
    """The user-visible repro: a scorecard cached before the fix keeps short-
    circuiting the analysis, whatever backend is configured now."""
    from tabs.image_gallery.use_cases import ai_analysis

    cache = _cache_dir(tmp_path, monkeypatch)
    path = Path("/gallery/frame.png")
    _write_legacy_entry(cache, path, 42, description="previous backend's read")

    started: list = []
    owner = SimpleNamespace(
        state=SimpleNamespace(mode="camera", metric_profile=None, items=[]),
        widget=SimpleNamespace(refresh_card=lambda it: None),
        _ai_settings_store=SimpleNamespace(load=lambda: _settings(model="model/B")),
        _begin_analysis=lambda it: started.append(it),
    )
    item = SimpleNamespace(path=path, mtime_ns=42, analysis=None, analysis_status=None)

    ai_analysis.analyze_item(owner, item)

    assert item.analysis is None
    assert len(started) == 1


def test_analyze_item_hits_its_own_backend(tmp_path, monkeypatch) -> None:
    """The same identity still hits — the cache is not disabled wholesale."""
    from tabs.image_gallery.use_cases import ai_analysis

    _cache_dir(tmp_path, monkeypatch)
    path = Path("/gallery/frame.png")

    started: list = []
    owner = SimpleNamespace(
        state=SimpleNamespace(mode="camera", metric_profile=None, items=[]),
        widget=SimpleNamespace(refresh_card=lambda it: None),
        _ai_settings_store=SimpleNamespace(load=lambda: _settings()),
        _begin_analysis=lambda it: started.append(it),
    )
    expected = _result()
    # Seed with the owner's OWN identity — the lookup the analyze path performs.
    ai_cache.save_analysis(path, 42, expected, ai_analysis.analysis_identity_for(owner))

    item = SimpleNamespace(path=path, mtime_ns=42, analysis=None)

    ai_analysis.analyze_item(owner, item)

    assert item.analysis is not None
    assert item.analysis.description == expected.description
    assert item.analysis.sharpness == expected.sharpness
    assert started == []


# ---------------------------------------------------------------------------
# identity fields: every one of them rejects a cached result
# ---------------------------------------------------------------------------


def test_identity_rejects_a_different_model(tmp_path, monkeypatch) -> None:
    _cache_dir(tmp_path, monkeypatch)
    path, mtime = Path("/gallery/a.png"), 7
    ai_cache.save_analysis(path, mtime, _result(), _identity())

    assert ai_cache.load_cached_analysis(path, mtime, _identity()) is not None
    assert (
        ai_cache.load_cached_analysis(
            path, mtime, _identity(_settings(model="model/B"))
        )
        is None
    )


def test_identity_rejects_a_different_base_url(tmp_path, monkeypatch) -> None:
    _cache_dir(tmp_path, monkeypatch)
    path, mtime = Path("/gallery/a.png"), 7
    ai_cache.save_analysis(path, mtime, _result(), _identity())

    assert (
        ai_cache.load_cached_analysis(
            path, mtime, _identity(_settings(base_url="http://localhost:8080/v1"))
        )
        is None
    )


def test_identity_rejects_a_different_mode(tmp_path, monkeypatch) -> None:
    _cache_dir(tmp_path, monkeypatch)
    path, mtime = Path("/gallery/a.png"), 7
    ai_cache.save_analysis(path, mtime, _result(), _identity())

    assert ai_cache.load_cached_analysis(path, mtime, _identity(mode="fidelity")) is None


def test_identity_rejects_a_different_profile(tmp_path, monkeypatch) -> None:
    _cache_dir(tmp_path, monkeypatch)
    path, mtime = Path("/gallery/a.png"), 7
    ai_cache.save_analysis(path, mtime, _result(), _identity())

    assert (
        ai_cache.load_cached_analysis(
            path, mtime, _identity(profile=("sharpness", "noise"))
        )
        is None
    )


def test_identity_rejects_a_different_reasoning_effort(tmp_path, monkeypatch) -> None:
    _cache_dir(tmp_path, monkeypatch)
    path, mtime = Path("/gallery/a.png"), 7
    ai_cache.save_analysis(path, mtime, _result(), _identity())

    assert (
        ai_cache.load_cached_analysis(
            path, mtime, _identity(reasoning_effort="high")
        )
        is None
    )


def test_identity_rejects_a_bumped_prompt_schema_version(tmp_path, monkeypatch) -> None:
    """Bumping ``PROMPT_SCHEMA_VERSION`` must invalidate every cached scorecard."""
    _cache_dir(tmp_path, monkeypatch)
    path, mtime = Path("/gallery/a.png"), 7
    ai_cache.save_analysis(path, mtime, _result(), _identity())

    bumped = _identity(schema_version=ai_cache.PROMPT_SCHEMA_VERSION + 1)
    assert ai_cache.load_cached_analysis(path, mtime, bumped) is None
    assert (
        ai_cache.load_cached_analysis(
            path, mtime, _identity(schema_version=ai_cache.PROMPT_SCHEMA_VERSION)
        )
        is not None
    )


# ---------------------------------------------------------------------------
# secrets never enter the key/payload; the payload identity is re-validated
# ---------------------------------------------------------------------------


def test_identity_ignores_the_api_key_and_has_no_secret() -> None:
    a = _identity(_settings(api_key="sk-first-value"))
    b = _identity(_settings(api_key="sk-other-value"))

    assert a == b, "rotating the API key must not invalidate the analysis cache"
    assert not any("secret" in str(v) for v in a.values())
    assert "api_key" not in a


def test_payload_stores_the_identity_but_never_the_api_key(tmp_path, monkeypatch) -> None:
    cache = _cache_dir(tmp_path, monkeypatch)
    path, mtime = Path("/gallery/a.png"), 7
    ai_cache.save_analysis(path, mtime, _result(), _identity())

    files = list(cache.glob("*.json"))
    assert len(files) == 1
    text = files[0].read_text(encoding="utf-8")
    data = json.loads(text)

    assert data["identity"] == _identity()
    assert "sk-secret-value" not in text
    assert "api_key" not in data
    assert "api_key" not in data["identity"]
    assert files[0].name != f"{cache_key_for(path, mtime)}.json"  # identity in the key


def test_payload_identity_mismatch_is_a_miss_even_on_a_key_collision(
    tmp_path, monkeypatch
) -> None:
    """Defence in depth: the file key alone is not trusted."""
    cache = _cache_dir(tmp_path, monkeypatch)
    path, mtime = Path("/gallery/a.png"), 7
    identity = _identity()
    ai_cache.save_analysis(path, mtime, _result(), identity)

    cache_file = next(cache.glob("*.json"))
    data = json.loads(cache_file.read_text(encoding="utf-8"))
    data["identity"] = _identity(_settings(model="model/B"))  # simulate a collision
    cache_file.write_text(json.dumps(data), encoding="utf-8")

    assert ai_cache.load_cached_analysis(path, mtime, identity) is None


def test_legacy_pre_identity_entry_is_a_miss_not_a_migration(tmp_path, monkeypatch) -> None:
    """An old file (no identity, older version) is ignored — no crash, no upgrade."""
    cache = _cache_dir(tmp_path, monkeypatch)
    path, mtime = Path("/gallery/a.png"), 7
    ai_cache.save_analysis(path, mtime, _result(), _identity())

    saved = next(cache.glob("*.json"))
    data = json.loads(saved.read_text(encoding="utf-8"))
    data.pop("identity", None)
    data["version"] = 2  # pre-identity cache format
    legacy = cache / f"{cache_key_for(path, mtime)}.json"
    legacy.write_text(json.dumps(data), encoding="utf-8")
    saved.unlink()

    assert ai_cache.load_cached_analysis(path, mtime, _identity()) is None
    assert legacy.is_file(), "a legacy entry must not be migrated or swallowed"


def test_incomplete_identity_never_writes_an_unverifiable_entry(
    tmp_path, monkeypatch
) -> None:
    cache = _cache_dir(tmp_path, monkeypatch)
    ai_cache.save_analysis(Path("/gallery/a.png"), 7, _result(), {"model": "model/A"})
    assert list(cache.glob("*.json")) == []


def test_clear_removes_every_identity_for_the_image(tmp_path, monkeypatch) -> None:
    """A cache reset has no backend in hand: it must drop all variants."""
    _cache_dir(tmp_path, monkeypatch)
    path, mtime = Path("/gallery/a.png"), 7
    ai_cache.save_analysis(path, mtime, _result(), _identity())
    ai_cache.save_analysis(path, mtime, _result(), _identity(_settings(model="model/B")))

    assert ai_cache.clear_cached_analysis(path, mtime) is True
    assert ai_cache.load_cached_analysis(path, mtime, _identity()) is None
    assert (
        ai_cache.load_cached_analysis(path, mtime, _identity(_settings(model="model/B")))
        is None
    )
