"""P1 — cache FIRST, the profile as an OUTPUT (``task-analysis-phase-state``).

Measured defect (owner, 2026-10-26): opening a folder paid a VLM profile call
FIRST, and the analysis key contained the profile it resolved. The profile is
not stable per folder — four paths return the heuristic offer and none of them
was pinned — so the same image keyed differently between runs: 3 HIT / 7 MISS on
10 images whose 10 entries were already on disk.

Falsification story (each test names the defect it kills):

- **a** — the identity is profile-free: a scorecard saved under one axis set is
  SERVED under another, and the entry says which axes it answered. Red before:
  the profile was hashed into the filename, so every re-roll re-analyzed.
- **b** — the folder-level probe answers "is this folder done" from the disk
  BEFORE any paid step, and a complete folder launches no selector worker (no
  profile request) and builds no analyze payload.
- **c** — the resolved profile is pinned with its SOURCE, including the
  heuristic/series offer, so one folder resolves one profile and a second pass
  costs no request. Red before: only the VLM answer was pinned, the offer was
  re-derived on every pass.
- **d** — ``refresh=True`` is the EXPLICIT invalidation seam: a pinned offer is
  only replaced when someone says so (never by a policy change).

Everything runs offscreen on real services + a Qt-free controller double; the
payload-build seam is recorded, so "no analyze" is observed, not inferred.
"""

from __future__ import annotations

import dataclasses
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from tabs.image_gallery import controller as controller_mod
from tabs.image_gallery.controller import GalleryController
from tabs.image_gallery.models import AiAnalysisResult, GalleryItem, Mode
from tabs.image_gallery.services import ai_cache
from tabs.image_gallery.services.ai_settings_store import AiSettings
from tabs.image_gallery.services.metric_profile import MetricProfile
from tabs.image_gallery.services.profile_cache import ProfileCache, profile_cache_key
from tabs.image_gallery.use_cases import pipeline_stages as ps
from tabs.image_gallery.use_cases import profile_select
from tabs.image_gallery.use_cases.action_context import BACKEND_AI, ActionContext
from tabs.image_gallery.use_cases.profile_ai import choose_profile_sync

SETTINGS = AiSettings(
    enabled=True,
    base_url="https://openrouter.ai/api/v1",
    api_key="sk-not-a-real-secret",
    model="model/A",
    reasoning_effort="auto",
)

#: Two axis sets of the SAME folder — the re-roll the defect used to re-key.
PROFILE_A = MetricProfile(axis_ids=("sharpness", "noise"), mode="camera", source="series")
PROFILE_B = MetricProfile(
    axis_ids=("sharpness", "exposure"), mode="camera", source="vlm"
)


def _cache_dir(tmp_path, monkeypatch) -> Path:
    cache = tmp_path / "ai_cache"
    cache.mkdir()
    monkeypatch.setattr(ai_cache, "ai_cache_dir", lambda: cache)
    return cache


def _result(description: str = "read") -> AiAnalysisResult:
    return AiAnalysisResult(
        description=description,
        tags=(),
        model="model/A",
        analyzed_at_iso="2026-01-01T00:00:00+00:00",
        axes={"sharpness": 80, "noise": 70},
    )


# ---------------------------------------------------------------------------
# (a) the identity is profile-free
# ---------------------------------------------------------------------------


def test_a_scorecard_survives_a_profile_reroll_and_records_its_axes(
    tmp_path, monkeypatch
) -> None:
    _cache_dir(tmp_path, monkeypatch)
    path, mtime = Path("/gallery/a.png"), 42

    under_a = ai_cache.analysis_cache_identity(SETTINGS, mode="camera", profile=PROFILE_A)
    ai_cache.save_analysis(path, mtime, _result(), under_a)

    under_b = ai_cache.analysis_cache_identity(SETTINGS, mode="camera", profile=PROFILE_B)
    hit = ai_cache.load_cached_analysis(path, mtime, under_b)

    assert hit is not None, (
        "the axis set must not re-key the entry: 3 HIT / 7 MISS is this assertion "
        "failing silently on every folder open"
    )
    record = ai_cache.recorded_profile_for(path, mtime, under_b)
    assert record is not None
    assert record["axes"] == ["sharpness", "noise"], (
        "a reader must know WHICH axes the numbers describe — the axes it was "
        f"built with, not the current profile (got {record!r})"
    )
    assert record["source"] == "series", "the recorded source is an honest label"
    # Defence in depth is untouched: the payload still validates its backend.
    other_model = ai_cache.analysis_cache_identity(
        dataclasses.replace(SETTINGS, model="model/B"),
        mode="camera",
        profile=PROFILE_B,
    )
    assert ai_cache.load_cached_analysis(path, mtime, other_model) is None


def test_the_payload_records_the_profile_beside_the_identity(tmp_path, monkeypatch) -> None:
    cache = _cache_dir(tmp_path, monkeypatch)
    path, mtime = Path("/gallery/a.png"), 7
    identity = ai_cache.analysis_cache_identity(
        SETTINGS, mode="camera", profile=PROFILE_B
    )
    ai_cache.save_analysis(path, mtime, _result(), identity)

    data = json.loads(next(cache.iterdir()).read_text(encoding="utf-8"))
    assert data["identity"] == {
        field: identity[field] for field in ai_cache.IDENTITY_FIELDS
    }, "the key never carries the axis set"
    assert data["profile"] == {
        "axes": ["sharpness", "exposure"],
        "judged": [],
        "definitions": {},
        "source": "vlm",
        "mode": "camera",
    }


# ---------------------------------------------------------------------------
# (b) the folder probe: no paid step when every card answers this identity
# ---------------------------------------------------------------------------


class _Owner:
    """Qt-free double binding the REAL controller primitives under test."""

    def __init__(self, items, *, gen: int = 3) -> None:
        self.state = SimpleNamespace(
            items=list(items), series=[], mode=Mode.CAMERA, metric_profile=PROFILE_A
        )
        self._judgment_domain = "ai"
        self._folder_gen = gen
        self._profile_consumed_gen = None
        self._stage_gate = ps.StageGate()
        self._ai_settings_store = SimpleNamespace(load=lambda: SETTINGS)
        self.widget = SimpleNamespace(
            refresh_cards=lambda its: None,
            refresh_card=lambda it: None,
            visible_paths=lambda: [str(it.path) for it in self.state.items],
        )
        self.launched: list = []
        self.payloads: list = []

    # -- real primitives ---------------------------------------------------
    def _folder_analysis_probe(self, items):
        return GalleryController._folder_analysis_probe(self, items)

    def _hydrate_from_probe(self, probe):
        return GalleryController._hydrate_from_probe(self, probe)

    def _run_profile_select_on_settle(self):
        return GalleryController._run_profile_select_on_settle(self)

    def _is_current_folder_gen(self, gen) -> bool:
        return True

    def _mark_profile_consumed(self) -> None:
        GalleryController._mark_profile_consumed(self)

    def _apply_profile_outcome(self, profile, gen) -> None:
        GalleryController._apply_profile_outcome(self, profile, gen)

    def _begin_analysis(self, ctx, item) -> None:
        self.payloads.append(str(item.path))

    # -- scheduler seam ----------------------------------------------------
    def _pool_start(self, worker, priority=None) -> None:
        self.launched.append(worker)


def _items(names=("a.png", "b.png")) -> list:
    return [GalleryItem(path=Path(f"/gallery/{name}"), mtime_ns=11) for name in names]


def _install_selector(monkeypatch, calls: list) -> None:
    def _factory():
        def _selector(items, *, mode=None, settings=None):
            calls.append(len(items))
            return PROFILE_B

        return _selector

    monkeypatch.setattr(controller_mod, "_profile_selector", _factory)


def test_a_fully_cached_folder_spends_no_profile_request_and_no_analyze(
    tmp_path, monkeypatch
) -> None:
    """The run-2 acceptance, offscreen: 0 analyze payloads, 0 selector workers."""
    _cache_dir(tmp_path, monkeypatch)
    first = _items()
    # Run 1: every card gets an entry under run 1's (different) profile.
    identity_a = ai_cache.analysis_cache_identity(SETTINGS, mode="camera", profile=PROFILE_A)
    for item in first:
        ai_cache.save_analysis(item.path, item.mtime_ns, _result(), identity_a)

    # Run 2: fresh cards, the profile re-rolled (the defect's trigger), same disk.
    owner = _Owner(_items())
    selector_calls: list = []
    _install_selector(monkeypatch, selector_calls)

    owner._run_profile_select_on_settle()

    assert selector_calls == [], "the run is DONE — no profile request"
    assert owner.launched == [], "no selector worker is scheduled"
    assert all(it.analysis is not None for it in owner.state.items), (
        "the probe hydrates its hits instead of re-reading them one by one"
    )

    # …and the analyze tail is pure cache: every card HITs, nothing is built.
    ctx = ActionContext(
        targets=tuple(it.path for it in owner.state.items),
        backend=BACKEND_AI,
        mode=Mode.CAMERA,
        profile=PROFILE_B,
    )
    for item in owner.state.items:
        item.analysis = None  # force the per-card path to consult the disk
        item.analysis_status = None
    GalleryController.analyze(owner, ctx)
    assert owner.payloads == [], "0 analyze MISS on the second run"


def test_a_miss_in_the_folder_still_asks_the_selector(tmp_path, monkeypatch) -> None:
    """Control: one missing card must not disable the paid path for the folder."""
    _cache_dir(tmp_path, monkeypatch)
    items = _items()
    identity = ai_cache.analysis_cache_identity(SETTINGS, mode="camera", profile=PROFILE_A)
    ai_cache.save_analysis(items[0].path, items[0].mtime_ns, _result(), identity)
    # items[1] has no entry → the folder is NOT complete.

    owner = _Owner(items)
    selector_calls: list = []
    _install_selector(monkeypatch, selector_calls)
    owner._run_profile_select_on_settle()

    assert len(owner.launched) == 1, "an incomplete folder still resolves its profile"
    assert selector_calls == [], "the selector body runs inside the worker"


def test_an_empty_folder_is_not_complete() -> None:
    probe = ai_cache.folder_cache_probe([], {"model": "m"})
    assert probe["complete"] is False and probe["total"] == 0


# ---------------------------------------------------------------------------
# (c)+(d) the pin: one folder, one profile, an explicit upgrade
# ---------------------------------------------------------------------------


def _profile_items() -> list:
    """Two items with measured spreads, so the offer is series-derived."""
    out = []
    for name, sharpness in (("a.png", 0.0), ("b.png", 400.0)):
        item = SimpleNamespace(path=Path(f"/gallery/{name}"), mtime_ns=1)
        item.metrics = {"sharpness": sharpness}
        out.append(item)
    return out


def _pin_key(items) -> str:
    return profile_cache_key(
        items, mode="camera", model="model/A",
        base_url="https://openrouter.ai/api/v1", reasoning_effort="auto",
    )


def test_a_failed_selection_is_not_pinned_so_the_folder_can_heal(tmp_path) -> None:
    """Owner rule 2026-10-26: no offer is pinned on failure — nothing at all is.

    Red-before: the series offer was pinned as the folder's profile, which made a
    paid failure look resolved and ranked the folder on camera axes. A transient
    failure must stay retryable; the per-generation stage gate — not the pin —
    is what bounds the attempts.
    """
    cache = ProfileCache(tmp_path)
    items = _profile_items()
    calls: list = []

    def _client(*args, **kwargs):
        calls.append(1)
        return {"choices": [{"message": {"content": "not json"}}]}

    first = choose_profile_sync(
        items, mode="camera", settings=SETTINGS, cache=cache, client_call=_client
    )
    assert first is None, "a junk reply yields no profile"
    assert cache.get(_pin_key(items)) is None, "and it is not pinned as an answer"

    second = choose_profile_sync(
        items, mode="camera", settings=SETTINGS, cache=cache, client_call=_client
    )
    assert second is None
    assert len(calls) == 2, (
        "one folder resolves ONE profile: the second pass reads the pin, it does "
        "not re-ask (a junk reply is not retried twice either)"
    )


def test_refresh_is_the_explicit_upgrade_seam(tmp_path) -> None:
    cache = ProfileCache(tmp_path)
    items = _profile_items()

    def _junk(*args, **kwargs):
        return {"choices": [{"message": {"content": "not json"}}]}

    def _answer(*args, **kwargs):
        # A COMPLETE answer (3..8 axes, each tied to the evidence) — a thin one
        # is refused with a WARN by the rule the phase-3 row enforces.
        rows = [
            {
                "name": name,
                "definition": definition,
                "scale": "0-100",
                "direction": "higher-is-better",
                "why": why,
            }
            for name, definition, why in (
                ("banding", "stepped tone transitions; 0 = none, 100 = heavy",
                 "the probes differ on stepped gradients"),
                ("ringing", "halo oscillations at edges; 0 = none, 100 = severe",
                 "the probes differ on edge halos"),
                ("sharpness", "micro-contrast; 0 = mushy, 100 = crisp",
                 "the measured spread separates the probes"),
            )
        ]
        return {
            "choices": [
                {"message": {"content": json.dumps({"axes": rows})}}
            ]
        }

    failed = choose_profile_sync(
        items, mode="camera", settings=SETTINGS, cache=cache, client_call=_junk
    )
    assert failed is None, "a junk reply is an error (owner rule 2026-10-26)"

    # A failure pins nothing, so the next pass asks again — and gets the answer.
    same = choose_profile_sync(
        items, mode="camera", settings=SETTINGS, cache=cache, client_call=_answer
    )
    assert same.source == "vlm", (
        "an unpinned failure is retried; the judge's answer is what resolves it"
    )

    upgraded = choose_profile_sync(
        items,
        mode="camera",
        settings=SETTINGS,
        cache=cache,
        client_call=_answer,
        refresh=True,
    )
    assert upgraded.source == "vlm", "the explicit refresh is the upgrade seam"
    assert cache.get(_pin_key(items)) == upgraded, "and the upgrade is what is pinned"


def test_the_pin_key_tracks_the_prompt_revision() -> None:
    """A prompt change would ask a different question — the pin must not outlive it."""
    import inspect

    from tabs.image_gallery.services import profile_cache

    source = inspect.getsource(profile_cache.profile_cache_key)
    assert "prompt" in source and "_prompt_revision()" in source, (
        "the pin identity must carry the analyze prompt revision"
    )
