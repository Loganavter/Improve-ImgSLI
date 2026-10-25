"""P2 — the VLM axis-set answer survives a cache-only run, and a drop is visible.

``plan-gallery-ai-judgement-2026-10-21`` §P2 / verified defect **J3** against
invariants **M5** ("every loss is a visible state with a cause") and **M1**
(one instrument: the profile is part of a request's cache identity).

Falsification story (each test names the defect it kills):

- **a** — a run whose every card is a disk-cache HIT builds no request, so the
  generation is NOT frozen and the paid VLM axis-set answer is applied to it.
  Red before P2: ``analyze`` stamped the freeze on entry
  (``_stamp_profile_consumed`` at the entry point), so an all-HIT run dropped the
  answer for the whole generation — live 2026-10-21, six HITs at 19:11:49 →
  "late vlm reply dropped — profile frozen for gen 2 (AI calls already built
  under it)" at 19:11:52, a parenthetical that was false for that run.
- **b** — a reply landing after a request of the same generation WAS built is
  still rejected (the freeze keeps scorecards readable by the next open), but the
  rejection now sets ``state.profile_reject_reason`` and traces the reason
  instead of vanishing into one debug line.

The real ``GalleryController`` entry / stamp / apply methods run on a Qt-free
double; only the payload-build seam (``_begin_analysis``) and the disk cache are
substituted, so "a payload was built" is observed, not assumed.
"""

from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace

import pytest

from tabs.image_gallery.controller import GalleryController
from tabs.image_gallery.models import AiAnalysisResult, GalleryItem
from tabs.image_gallery.services.metric_profile import (
    PROFILE_REJECT_CALLS_BUILT,
    MetricProfile,
    profile_for_mode,
)
from tabs.image_gallery.use_cases import ai_analyze
from tabs.image_gallery.use_cases.action_context import BACKEND_AI, ActionContext
from core.log_names import APP_LOGGER_NAME

VLM_PROFILE = MetricProfile(
    axis_ids=("sharpness", "noise"), mode="camera", source="vlm",
    salient_axes=("sharpness", "noise"),
)


class _Owner:
    """Duck-typed controller: real ``analyze`` → real ``_analyze_ai``, no Qt.

    ``_begin_analysis`` is the payload-build seam (``ai_analyze`` calls it for
    every cache MISS): it is recorded instead of executed, so the test's
    ``payloads`` list is the fact "a request was built", not a guess.
    """

    def __init__(self, paths: tuple[Path, ...], *, gen: int = 0) -> None:
        self.state = SimpleNamespace(
            items=[GalleryItem(path=path, mtime_ns=0) for path in paths],
            mode="camera",
            metric_profile=profile_for_mode("camera"),
            profile_reject_reason="",
        )
        self._judgment_domain = "ai"
        self._folder_gen = gen
        self._profile_consumed_gen = None
        self.widget = SimpleNamespace(
            visible_paths=lambda: [str(p) for p in paths],
            refresh_card=lambda item: None,
            refresh_cards=lambda items: None,
        )
        self._ai_settings_store = SimpleNamespace(
            load=lambda: SimpleNamespace(
                model="m",
                base_url="https://example.invalid/v1",
                reasoning_effort="auto",
                enabled=True,
                api_key="test-key-not-a-secret",
            )
        )
        self.payloads: list[str] = []

    # -- real controller primitives bound to this fake ----------------------
    def _begin_analysis(self, ctx, item) -> None:  # type: ignore[no-untyped-def]
        self.payloads.append(str(item.path))

    def _mark_profile_consumed(self) -> None:
        GalleryController._mark_profile_consumed(self)

    def _apply_profile_outcome(self, profile, gen) -> None:  # type: ignore[no-untyped-def]
        GalleryController._apply_profile_outcome(self, profile, gen)

    def _is_current_folder_gen(self, gen) -> bool:  # type: ignore[no-untyped-def]
        return GalleryController._is_current_folder_gen(self, gen)

    def _tr(self, key: str, default: str) -> str:
        return default


def _cached_analysis() -> AiAnalysisResult:
    return AiAnalysisResult(
        description="", tags=(), model="m", analyzed_at_iso="t", axes={"sharpness": 80}
    )


def _drive_analyze(monkeypatch, owner: _Owner, *, hit: bool) -> None:
    """Run the REAL analyze entry with the cache seam pinned to *hit*."""
    cached = _cached_analysis() if hit else None
    monkeypatch.setattr(
        ai_analyze, "load_cached_analysis", lambda path, mtime, identity: cached
    )
    monkeypatch.setattr(
        ai_analyze, "analysis_identity_for", lambda owner_, ctx=None: {"model": "m"}
    )
    ctx = ActionContext(
        targets=tuple(it.path for it in owner.state.items),
        backend=BACKEND_AI,
        mode="camera",
    )
    assert GalleryController.analyze(owner, ctx) is None


def test_cache_only_analyze_keeps_the_generation_open_and_applies_the_answer(
    monkeypatch, caplog
) -> None:
    """(a) no payload built → no freeze → the paid axis-set answer lands."""
    paths = (Path("/gallery/hit_1.png"), Path("/gallery/hit_2.png"))
    owner = _Owner(paths)

    _drive_analyze(monkeypatch, owner, hit=True)

    assert owner.payloads == [], "a cache HIT builds no request payload"
    assert owner._profile_consumed_gen is None, (
        "a cache-only run froze the generation, so the VLM answer for it will be "
        "dropped as 'late' although no call was ever built (J3)"
    )

    with caplog.at_level(logging.DEBUG, logger=APP_LOGGER_NAME):
        owner._apply_profile_outcome(VLM_PROFILE, owner._folder_gen)

    assert owner.state.metric_profile is VLM_PROFILE, (
        "the axis-set answer must be applied inside the same generation when no "
        "request was built under the previous set"
    )
    assert owner.state.profile_reject_reason == "", "nothing was rejected here"
    assert not [
        rec for rec in caplog.records if "rejected" in rec.getMessage().lower()
    ], "an applied profile must not be logged as a rejection"


def test_reply_after_a_built_request_is_rejected_with_a_visible_reason(
    monkeypatch, caplog
) -> None:
    """(b) a built request still freezes the generation — and says why."""
    paths = (Path("/gallery/miss_1.png"), Path("/gallery/miss_2.png"))
    owner = _Owner(paths)
    heuristic = owner.state.metric_profile

    _drive_analyze(monkeypatch, owner, hit=False)

    assert owner.payloads == [str(p) for p in paths], (
        "the fixture must take the real MISS branch: one payload per card"
    )
    assert owner._profile_consumed_gen == owner._folder_gen, (
        "building a request IS the fact that freezes the profile (P5/P2)"
    )

    with caplog.at_level(logging.DEBUG, logger=APP_LOGGER_NAME):
        owner._apply_profile_outcome(VLM_PROFILE, owner._folder_gen)

    assert owner.state.metric_profile is heuristic, (
        "a reply landing after a request was built may not re-key that "
        "generation's scorecards"
    )
    assert owner.state.profile_reject_reason == PROFILE_REJECT_CALLS_BUILT, (
        "a dropped axis-set answer is a LOSS the UI must be able to show, with "
        f"its cause encoded (got {owner.state.profile_reject_reason!r})"
    )
    assert any(
        "rejected" in rec.getMessage().lower()
        and "already built" in rec.getMessage().lower()
        for rec in caplog.records
    ), "the drop must say WHY in the trace, not only that it happened"


def test_the_freeze_is_generation_scoped_so_the_next_folder_still_accepts(
    monkeypatch,
) -> None:
    """A stale generation's answer is rejected; the next one is not blocked.

    The freeze exists per folder generation (a profile is a request identity),
    so it may never leak forward and silently disable the selector for the rest
    of the session.
    """
    paths = (Path("/gallery/g1_1.png"), Path("/gallery/g1_2.png"))
    owner = _Owner(paths, gen=1)
    _drive_analyze(monkeypatch, owner, hit=False)
    assert owner._profile_consumed_gen == 1

    # The folder changed: a fresh state, a new generation, nothing consumed.
    owner._folder_gen = 2
    owner.state.metric_profile = profile_for_mode("camera")
    owner.state.profile_reject_reason = ""

    owner._apply_profile_outcome(VLM_PROFILE, 2)

    assert owner.state.metric_profile is VLM_PROFILE, (
        "the freeze must not survive its generation: an all-HIT or empty next "
        "folder would never receive the model's axis set"
    )
    assert owner.state.profile_reject_reason == ""
