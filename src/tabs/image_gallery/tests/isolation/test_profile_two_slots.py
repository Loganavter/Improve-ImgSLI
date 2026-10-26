"""INVARIANT: the two backends own one profile slot each, and nothing reads the other's.

``state.metric_profile`` was one slot written by the LOCAL derivation and by the
VLM judge, and read by both. Consequence (measured in the audit): a judge answer
governed the Algorithms order and a local offer governed the AI prompt. This
suite pins the split:

* each WRITER (the real controller methods) lands in its own slot and leaves the
  other slot untouched;
* ``profile_for_domain`` is the ONE reader and raises on a foreign-tagged slot;
* the AI accessor has NO local fallback — an empty AI slot is an EMPTY judge
  profile, never the local detectors' axis set (owner invariant I1);
* the real prompt builder and the real rank helpers can only see their own slot:
  the AI prompt asks the judge's axes, the Algorithms rank measures the local
  ones.

Red before the split: ``active_profile`` had no ``domain`` argument and read the
single slot, so an AI answer was what the Algorithms rank consumed.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from tabs.image_gallery.controller import GalleryController
from tabs.image_gallery.models import AiAxisProposal, GalleryItem, GalleryState
from tabs.image_gallery.services.ai_client.prompt import build_prompt
from tabs.image_gallery.services.metric_profile import (
    DOMAIN_AI,
    DOMAIN_ALGORITHMS,
    ForeignProfileError,
    MetricProfile,
    profile_for_domain,
    profile_for_mode,
)
from tabs.image_gallery.services.profile_judged import judged_axis_entries
from tabs.image_gallery.services.rank_fusion import (
    item_quality,
    measured_axes_for,
    rank_series,
)
from tabs.image_gallery.use_cases.action_context import _analysis_parameters
from tabs.image_gallery.use_cases.profile_select import active_profile

JUDGE_AXIS = "halation"


def _state(**slots) -> GalleryState:
    return GalleryState(mode="camera", **slots)


def _local_profile() -> MetricProfile:
    return MetricProfile(
        axis_ids=("sharpness", "noise"), mode="camera", source="series"
    )


def _judge_profile() -> MetricProfile:
    return MetricProfile(
        mode="camera",
        source="vlm",
        axis_entries=(
            AiAxisProposal(
                name=JUDGE_AXIS,
                definition="how much glow surrounds bright edges",
                direction="lower-is-better",
            ),
        ),
    )


# ---------------------------------------------------------------------------
# writers: each real producer owns exactly one slot
# ---------------------------------------------------------------------------


class _WriterOwner:
    """Duck-typed controller running the REAL profile writers (no Qt)."""

    def __init__(self, *, domain: str = "ai", items=None) -> None:
        self.state = SimpleNamespace(
            items=list(items or []),
            series=[],
            mode="camera",
            source_path=None,
            algorithms_profile=None,
            ai_profile=None,
            profile_reject_reason="",
        )
        self._judgment_domain = domain
        self._folder_gen = 0
        self._profile_consumed_gen = None
        self.widget = SimpleNamespace(
            refresh_cards=lambda _items: None,
            refresh_card=lambda _item: None,
        )

    def refresh_metric_profile(self):
        return GalleryController.refresh_metric_profile(self)

    def _apply_profile_outcome(self, profile, gen):
        return GalleryController._apply_profile_outcome(self, profile, gen)

    def _is_current_folder_gen(self, gen):
        return GalleryController._is_current_folder_gen(self, gen)

    def _mark_ai_profile_error(self, reason):
        GalleryController._mark_ai_profile_error(self, reason)

    def clear_metric_profile(self):
        return GalleryController.clear_metric_profile(self)


def _measured_item(name: str, sharpness: float) -> GalleryItem:
    item = GalleryItem(path=Path(f"/gallery/{name}"), mtime_ns=1)
    item.metrics.update({"sharpness": sharpness})
    return item


def test_the_local_writer_never_touches_the_ai_slot() -> None:
    judge = _judge_profile()
    owner = _WriterOwner(
        domain="algorithms",
        items=[_measured_item("a.png", 0.0), _measured_item("b.png", 400.0)],
    )
    owner.state.ai_profile = judge

    owner.refresh_metric_profile()

    assert owner.state.ai_profile is judge, (
        "the local derivation overwrote the judge's answer — one mutable slot again"
    )
    local = owner.state.algorithms_profile
    assert local is not None and local.source in ("series", "heuristic")


def test_the_judge_writer_never_touches_the_algorithms_slot() -> None:
    local = _local_profile()
    judge = _judge_profile()
    owner = _WriterOwner(domain="ai")
    owner.state.algorithms_profile = local

    owner._apply_profile_outcome(judge, owner._folder_gen)

    assert owner.state.ai_profile is judge, "the VLM answer must land in ai_profile"
    assert owner.state.algorithms_profile is local, (
        "the judge's answer overwrote the Algorithms backend's own measurements"
    )


def test_clear_drops_both_slots() -> None:
    owner = _WriterOwner()
    owner.state.algorithms_profile = _local_profile()
    owner.state.ai_profile = _judge_profile()

    owner.clear_metric_profile()

    assert owner.state.algorithms_profile is None
    assert owner.state.ai_profile is None


# ---------------------------------------------------------------------------
# the strict reader: empty is empty, foreign is loud, unknown is loud
# ---------------------------------------------------------------------------


def test_each_writer_lands_in_its_own_slot() -> None:
    state = _state()
    local, judge = _local_profile(), _judge_profile()

    state.algorithms_profile = local
    assert state.ai_profile is None
    assert profile_for_domain(state, DOMAIN_ALGORITHMS) is local

    state.ai_profile = judge
    assert profile_for_domain(state, DOMAIN_ALGORITHMS) is local
    assert profile_for_domain(state, DOMAIN_AI) is judge
    assert local.axis_entries == () and judge.axis_ids == ()


def test_the_ai_reader_never_returns_the_algorithms_profile() -> None:
    local = _local_profile()
    state = _state(algorithms_profile=local)

    # The chosen contract: an empty slot reads as ``None`` — "the AI backend has
    # not answered" — never the other backend's profile.
    assert profile_for_domain(state, DOMAIN_AI) is None
    assert profile_for_domain(state, DOMAIN_ALGORITHMS) is local


def test_a_foreign_tag_is_loud_at_the_strict_seam() -> None:
    state = _state(algorithms_profile=_judge_profile())
    with pytest.raises(ForeignProfileError):
        profile_for_domain(state, DOMAIN_ALGORITHMS)

    state = _state(ai_profile=_local_profile())
    with pytest.raises(ForeignProfileError):
        profile_for_domain(state, DOMAIN_AI)

    with pytest.raises(ValueError):
        profile_for_domain(state, "judge")


def test_the_ai_accessor_has_no_local_fallback() -> None:
    local = _local_profile()
    state = _state(algorithms_profile=local)

    ai = active_profile(state, domain=DOMAIN_AI)
    assert ai.axis_entries == ()
    assert ai.axis_ids == ()
    assert not ai, "an empty AI slot must be EMPTY, not the local mode mapping"

    algo = active_profile(state, domain=DOMAIN_ALGORITHMS)
    assert algo is local
    assert JUDGE_AXIS not in measured_axes_for("camera", profile=algo)
    assert measured_axes_for("camera", profile=algo) == local.axis_ids


def test_each_consumer_family_reads_only_its_slot() -> None:
    local, judge = _local_profile(), _judge_profile()
    state = _state(algorithms_profile=local, ai_profile=judge)

    algo = profile_for_domain(state, DOMAIN_ALGORITHMS)
    ai = profile_for_domain(state, DOMAIN_AI)

    # The local rank vocabulary: registry ids only, no judge names.
    assert measured_axes_for("camera", profile=algo) == local.axis_ids
    assert JUDGE_AXIS not in measured_axes_for("camera", profile=algo)

    # The judge vocabulary: the model's own names, not the local axis list.
    assert [entry.name for entry in judged_axis_entries(ai)] == [JUDGE_AXIS]
    assert judged_axis_entries(algo) == ()

    # The mode mapping is a LOCAL producer: it may only feed the local accessor.
    mode_profile = profile_for_mode("camera")
    assert mode_profile.source == "heuristic"
    assert active_profile(
        SimpleNamespace(mode="camera", algorithms_profile=None, ai_profile=None),
        domain=DOMAIN_AI,
    ).axis_ids == ()


# ---------------------------------------------------------------------------
# the REAL prompt / rank helpers: the AI asks the AI slot, the rank measures the
# Algorithms slot — with both slots populated, so a shared slot is caught.
# ---------------------------------------------------------------------------


def _prompt_state() -> GalleryState:
    """Algorithms measures ``sharpness``; the judge asked for ``halation``."""
    return _state(
        algorithms_profile=MetricProfile(
            axis_ids=("sharpness",), mode="camera", source="series"
        ),
        ai_profile=MetricProfile(
            axis_ids=("noise",),
            mode="camera",
            source="vlm",
            axis_entries=(
                AiAxisProposal(
                    name=JUDGE_AXIS,
                    definition="bright edges bloom into a soft halo",
                    direction="lower-is-better",
                ),
            ),
        ),
    )


def test_the_ai_prompt_is_built_from_the_ai_slot_only() -> None:
    state = _prompt_state()
    owner = SimpleNamespace(
        _judgment_domain="ai",
        state=state,
        _ai_settings_store=SimpleNamespace(
            load=lambda: SimpleNamespace(reasoning_effort=None)
        ),
    )

    params = _analysis_parameters(owner)  # the REAL context/profile snapshot
    assert params["backend"] == "ai"
    assert params["profile"] is profile_for_domain(state, DOMAIN_AI)

    prompt = build_prompt(params["mode"], profile=params["profile"])
    assert f'"{JUDGE_AXIS}"' in prompt, "the judge's own axis must be asked by name"
    assert '"noise"' in prompt, "the AI slot's registry axis must be asked"
    assert '"sharpness"' not in prompt, (
        "the AI prompt asked for a LOCAL axis — it read the Algorithms slot"
    )


def test_the_algorithms_rank_input_is_the_algorithms_slot_only() -> None:
    state = _prompt_state()
    algo = profile_for_domain(state, DOMAIN_ALGORITHMS)
    ai = profile_for_domain(state, DOMAIN_AI)

    # The rank's own axis resolver: registry ids from the Algorithms profile.
    assert measured_axes_for("camera", profile=algo) == ("sharpness",)
    assert JUDGE_AXIS not in measured_axes_for("camera", profile=algo)

    # Two variants with IDENTICAL local sharpness and DIFFERENT local noise.
    a = GalleryItem(path=Path("/gallery/a.png"), mtime_ns=1)
    b = GalleryItem(path=Path("/gallery/b.png"), mtime_ns=1)
    a.metrics.update({"sharpness": 200.0, "noise": 0.9})
    b.metrics.update({"sharpness": 200.0, "noise": 0.0})

    # Algorithms profile measures sharpness only → a real tie, broken by path.
    assert item_quality(a, profile=algo) == item_quality(b, profile=algo)
    assert rank_series([a, b], profile=algo) == {
        str(a.path): 1,
        str(b.path): 2,
    }
    # ...while the AI profile (noise) WOULD separate them — non-vacuity: the tie
    # above is caused by the slot, not by identical fixtures.
    assert item_quality(a, profile=ai) != item_quality(b, profile=ai)
    assert rank_series([a, b], profile=ai) != rank_series([a, b], profile=algo)


def test_the_two_slots_are_independent_state() -> None:
    """A single-slot regression cannot satisfy this: the two objects differ."""
    state = _prompt_state()
    assert state.algorithms_profile is not state.ai_profile
    assert profile_for_domain(state, DOMAIN_ALGORITHMS) is not profile_for_domain(
        state, DOMAIN_AI
    )
    assert not hasattr(state, "metric_profile"), (
        "the deleted single slot must not remain as a silent alias"
    )
