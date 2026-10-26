"""INVARIANT (ADR 009 wave A3): an empty AI profile is NOT the local mode mapping.

The leak this suite pins: ``rank_fusion.measured_axes_for`` used to answer the
LOCAL mode axes whenever the profile it was handed carried no axis —
``if profile is not None: ... if out: return out`` fell through to
``return profile_for_mode(mode).axis_ids``. An EMPTY AI profile is
falsy-but-present, so every AI-domain consumer that resolved its axis set
through ``profile_judged.scorecard_axis_ids`` silently got the DETECTOR axis
list instead of "not ready":

1. the card action → ``action_context._analysis_parameters`` → the request
   build → ``ai_client.prompt.build_prompt`` (asked the model for local axes);
2. the AI request's custom-prompt path → ``attach_measured_context`` (echo
   filter resolved the local set, so local numbers were attached as context);
3. the Jev vector → ``jev_client.build_measured_vector`` (vector built over
   local axes);
4. the card dots → ``ui.card.dots.metric_dots_for_item`` (drew local dots);
5. the pairwise payload → ``pairwise_rank.profile_axis_numbers`` (local
   aggregates went into an AI-domain payload);
6. the cross-series priority payload → ``series_priority._signal_entry`` (it
   called ``rank_fusion.item_quality(mode=…)`` with no profile at all).

Falsification story (red at ``rank_fusion.py`` §``measured_axes_for``, the
``profile_for_mode`` tail): each test below reaches the fallback on the base
commit and now gets ``NoProfileYet`` / "not ready". The non-vacuity halves keep
them honest: a REAL profile still asks/measures/renders exactly its own axes,
so the refusal is about EMPTY, not about the AI domain.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from tabs.image_gallery.backends import NoProfileYet
from tabs.image_gallery.backends.ai import BACKEND as AI_BACKEND
from tabs.image_gallery.backends.composition import backend
from tabs.image_gallery.models import (
    AiAnalysisResult,
    AiAxisProposal,
    GalleryItem,
    GalleryState,
)
from tabs.image_gallery.services import jev_cache
from tabs.image_gallery.services.ai_client.prompt import (
    attach_measured_context,
    build_prompt,
)
from tabs.image_gallery.services.jev_client import (
    JEV_REASON_NO_PROFILE,
    build_measured_vector,
    rank_series_jev_detailed,
)
from tabs.image_gallery.services.metric_profile import MetricProfile
from tabs.image_gallery.services.profile_judged import scorecard_axis_ids
from tabs.image_gallery.services.rank_fusion import measured_axes_for
from tabs.image_gallery.ui.card.dots import metric_dots_for_item
from tabs.image_gallery.use_cases.action_context import _analysis_parameters
from tabs.image_gallery.use_cases.pairwise_rank import profile_axis_numbers

JUDGE_AXIS = "halation"


# -- fixtures -----------------------------------------------------------------


def _empty_ai_profile() -> MetricProfile:
    """What an unfilled AI slot reads as: present, tagged, and axis-less."""
    return MetricProfile(mode="camera", source="vlm")


def _judge_profile() -> MetricProfile:
    return MetricProfile(
        mode="camera",
        source="vlm",
        axis_entries=(
            AiAxisProposal(
                name=JUDGE_AXIS,
                definition="glow around bright edges",
                scale="0-100",
                direction="lower-is-better",
            ),
        ),
    )


def _scored(name: str, **axes: int) -> GalleryItem:
    """A card the judge scored on *axes*."""
    item = GalleryItem(path=Path(f"/gallery/{name}"), mtime_ns=1)
    item.analysis = AiAnalysisResult(
        description="",
        tags=(),
        model="judge-model",
        analyzed_at_iso="t",
        axes=dict(axes),
        axis_proposals=tuple(
            AiAxisProposal(name=axis, definition=f"{axis} moves", score=score)
            for axis, score in axes.items()
        ),
    )
    return item


def _local(name: str, **metrics) -> GalleryItem:
    item = GalleryItem(path=Path(f"/gallery/{name}"), mtime_ns=1)
    item.metrics.update(metrics)
    return item


def _state(**slots) -> GalleryState:
    return GalleryState(mode="camera", **slots)


# -- the resolver itself ------------------------------------------------------


def test_the_empty_profile_is_no_profile_yet_and_names_the_ai_backend() -> None:
    with pytest.raises(NoProfileYet) as excinfo:
        measured_axes_for("camera", profile=_empty_ai_profile())

    assert "ai" in str(excinfo.value), (
        "the refusal must name the backend whose profile is empty, not a "
        f"generic error: {excinfo.value}"
    )


def test_the_mode_mapping_stays_reachable_without_a_profile() -> None:
    """Non-vacuity: the local mode axes still exist — for the LOCAL backend.

    The mode mapping is the Algorithms backend's own ``heuristic`` profile, so
    ``profile=None`` still answers with it (a huge part of the tree asks for it).
    What died is answering it on behalf of an EMPTY profile.
    """
    assert measured_axes_for("camera") == backend("algorithms").axes_for_mode("camera")
    assert "sharpness" in measured_axes_for("camera")


def test_the_ai_adapter_refuses_to_store_an_axis_less_profile() -> None:
    """The adapter boundary: the AI slot never holds "no axes" as an answer."""
    state = _state()

    with pytest.raises(NoProfileYet):
        AI_BACKEND.install(state, _empty_ai_profile())

    assert getattr(state, "ai_profile", None) is None


def test_the_asked_set_propagates_the_refusal() -> None:
    """``scorecard_axis_ids`` must not swallow it into ``()`` (a silent 0-axis ask)."""
    with pytest.raises(NoProfileYet):
        scorecard_axis_ids("camera", profile=_empty_ai_profile())

    # ...and the judge's own axis set is still exactly what it asks.
    assert scorecard_axis_ids("camera", profile=_judge_profile()) == (JUDGE_AXIS,)


# -- chain 1: the action context → the request build → the prompt -------------


def test_chain_1_the_action_context_hands_the_prompt_an_empty_profile() -> None:
    owner = SimpleNamespace(
        _judgment_domain="ai",
        state=_state(ai_profile=_empty_ai_profile()),
        _ai_settings_store=SimpleNamespace(
            load=lambda: SimpleNamespace(reasoning_effort=None)
        ),
    )

    params = _analysis_parameters(owner)  # the REAL action-context snapshot
    assert params["backend"] == "ai"
    assert not params["profile"], "the empty AI slot must read as EMPTY"

    with pytest.raises(NoProfileYet):
        build_prompt(params["mode"], profile=params["profile"])


def test_chain_1_the_prompt_still_asks_a_real_profile() -> None:
    prompt = build_prompt("camera", profile=_judge_profile())
    assert f'"{JUDGE_AXIS}"' in prompt
    assert '"sharpness"' not in prompt, (
        "a judge-only profile must not be widened to the local axis set"
    )


# -- chain 2: the request's custom-prompt echo filter ------------------------


def test_chain_2_the_echo_filter_refuses_an_empty_profile() -> None:
    block = "- Sharpness: 1.2 (quality 55%)"

    with pytest.raises(NoProfileYet):
        attach_measured_context("assess this", block, mode="camera", profile=_empty_ai_profile())


def test_chain_2_a_real_profile_still_filters_the_local_numbers() -> None:
    local_profile = MetricProfile(
        axis_ids=("sharpness",), mode="camera", source="series"
    )
    text = attach_measured_context(
        "assess this",
        "- Sharpness: 1.2 (quality 55%)\n- White balance: 0.2 (quality 82%)",
        mode="camera",
        profile=local_profile,
    )
    assert "Sharpness" not in text, "an asked axis' local number is an echo"
    assert "White balance" in text, "a non-asked axis' number is legitimate context"


# -- chain 3: the Jev measured vector ---------------------------------------


def test_chain_3_the_jev_vector_refuses_an_empty_profile() -> None:
    items = [_scored("a.png", **{JUDGE_AXIS: 70}), _scored("b.png", **{JUDGE_AXIS: 40})]

    with pytest.raises(NoProfileYet):
        build_measured_vector(items, mode="camera", domain="ai", profile=_empty_ai_profile())


def test_chain_3_the_jev_rank_reports_not_ready_without_a_profile(tmp_path) -> None:
    items = [_scored("a.png", **{JUDGE_AXIS: 70}), _scored("b.png", **{JUDGE_AXIS: 40})]
    calls: list[dict] = []

    outcome = rank_series_jev_detailed(
        items,
        mode="camera",
        client=lambda payload: calls.append(payload) or {},
        cache=jev_cache.JevRankCache(tmp_path),
        domain="ai",
        profile=_empty_ai_profile(),
    )

    assert outcome.ranks is None, "a profile-less AI rank produced ranks"
    assert outcome.reason == JEV_REASON_NO_PROFILE
    assert calls == [], "a profile-less AI rank reached the transport"


def test_chain_3_a_real_profile_carries_the_judge_axes_only() -> None:
    items = [_scored("a.png", **{JUDGE_AXIS: 70}), _scored("b.png", **{JUDGE_AXIS: 40})]
    vector = build_measured_vector(
        items, mode="camera", domain="ai", profile=_judge_profile()
    )
    assert [entry["scores"] for entry in vector["items"]] == [
        {JUDGE_AXIS: 70},
        {JUDGE_AXIS: 40},
    ]


# -- chain 4: the card dots --------------------------------------------------


def test_chain_4_the_card_dots_are_not_ready_without_a_profile() -> None:
    # The card the VLM SCORED on a registry axis: at the base commit the empty
    # profile widened to the local camera set, that axis resolved, and the dot
    # was painted — the AI backend rendering the local axis list.
    item = _scored("a.png", sharpness=70)
    item.metrics.update({"sharpness": 200.0})

    colors, infos = metric_dots_for_item(
        item, "camera", domain="ai", profile=_empty_ai_profile()
    )

    assert (colors, infos) == ((), ()), (
        "an empty AI profile drew dots (the local axis set) on an AI-domain card"
    )


def test_chain_4_a_real_profile_still_paints_its_measured_axis() -> None:
    item = _scored("a.png", **{JUDGE_AXIS: 70})
    colors, infos = metric_dots_for_item(
        item, "camera", domain="ai", profile=_judge_profile()
    )
    assert [label for label, _score in infos], "the judge's measured axis must dot"


# -- chain 5: the pairwise payload ------------------------------------------


def test_chain_5_the_pairwise_numbers_are_empty_without_a_profile() -> None:
    item = _local("a.png", sharpness=200.0)

    assert profile_axis_numbers(item, mode="camera", profile=_empty_ai_profile()) == {}, (
        "a LOCAL aggregate entered the AI pairwise payload"
    )


def test_chain_5_a_real_profile_reads_the_judge_number() -> None:
    item = _scored("a.png", **{JUDGE_AXIS: 70})
    assert profile_axis_numbers(item, mode="camera", profile=_judge_profile()) == {
        JUDGE_AXIS: 70.0
    }


# -- chain 6: the cross-series priority payload ------------------------------


def test_chain_6_series_priority_refuses_without_a_profile() -> None:
    """``_signal_entry`` used ``item_quality(mode=mode)`` — the LOCAL aggregate."""
    from tabs.image_gallery.services import series_priority

    series = [
        SimpleNamespace(
            id="a", members=[_local("a1.png", sharpness=300.0), _local("a2.png", sharpness=150.0)]
        ),
        SimpleNamespace(
            id="b", members=[_local("b1.png", sharpness=200.0), _local("b2.png", sharpness=260.0)]
        ),
    ]

    with pytest.raises(NoProfileYet):
        series_priority.build_series_signals(
            series, mode="camera", profile=_empty_ai_profile()
        )

    outcome = series_priority.route_series_priority_detailed(
        series,
        mode="camera",
        client=lambda _payload: pytest.fail(
            "a profile-less priority pass spent a transport call"
        ),
        cache=None,
        profile=_empty_ai_profile(),
    )
    assert outcome.priorities is None
    assert outcome.reason == series_priority.PRIORITY_REASON_NO_PROFILE
