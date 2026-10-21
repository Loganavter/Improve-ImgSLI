"""P7-A — the judge NAMES the axes (plan-gallery-ai-judgement §OWNER REVISION 2026-10-22).

The owner replaced the "choose from the pool" design: the VLM is shown EXAMPLES of
what an axis can be (not a menu), asked for **3..8 axes in free form** that most
differentiate THESE pictures, and an axis it names is a first-class entry (name +
definition + scale + direction), not a registry id it had to guess.

Falsification story (what each test would catch, and why it is red before):

- **(a)** the selector prompt offers examples-with-meanings and the 3..8 free-form
  instruction. Red before: the text opened with ``METRIC POOL — choose axis ids
  ONLY from this list`` and asked for ``{"axes": ["<id>", ...]}``.
- **(b)** an axis whose name is NOT in ``MEASURED_POOL`` and NOT in
  ``profile_for_mode(mode).axis_ids`` SURVIVES as a first-class entry — with its
  definition, its scale and its direction. Red before: ``parse_profile_reply``
  intersected the answer with the mode's axis set, so the name was dropped and the
  reply degraded to the heuristic (``MetricProfile`` could not carry an entry at
  all). The same test covers the registry id the mode cannot measure (``ssim`` in
  a camera folder): the filter is gone, the id stays.
- **(c)** a proposal with no definition is still refused WITH its reason — the
  guard against over-widening: "free" is not "anything".
- **(d)** the scorecard prompt asks for the chosen free axis BY NAME with its
  definition, and for the registry axes exactly as before.
- **(e)** a profile carrying a free axis still resolves ``measured_axes_for()`` for
  its registry part (the local rows/fusion keep reading real detector ids).

Red-before evidence for every one of these was produced on a pre-change scratch
copy of ``HEAD`` (``git archive HEAD``) — see ``DONE.md``.

Extra seams the same wave has to keep honest: the pin round-trips entries (a
re-open must not re-roll the judge's axes), the analyze cache identity covers the
judge's axes (a different question cannot serve an old scorecard), a free-only
answer is a USABLE profile (not "hollow"), and the two provenances stay labelled.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from tabs.image_gallery.controller import GalleryController
from tabs.image_gallery.models import AiAxisProposal, GalleryItem
from tabs.image_gallery.services.ai_cache import analysis_cache_identity
from tabs.image_gallery.services.ai_client.prompt import _scorecard_axes, build_prompt
from tabs.image_gallery.services.axis_choice import (
    AXIS_CHOICE_MAX,
    parse_axis_choices,
)
from tabs.image_gallery.services.axis_proposal import (
    REJECT_DEFINITION,
    REJECT_REPEAT,
    parse_proposals,
    refusal_reason,
)
from tabs.image_gallery.services.metric_profile import (
    MEASURED_POOL,
    PROVENANCE_JUDGE,
    PROVENANCE_LOCAL,
    MetricProfile,
    axis_provenance,
    format_profile,
    profile_for_mode,
)
from tabs.image_gallery.services.profile_cache import ProfileCache
from tabs.image_gallery.services.rank_fusion import measured_axes_for
from tabs.image_gallery.use_cases import profile_ai
from tabs.image_gallery.use_cases.profile_ai import parse_profile_reply
from tabs.image_gallery.use_cases.profile_probe import salience_summary
from tabs.image_gallery.use_cases.profile_select import active_profile

#: A free axis: no local detector, no registry id — the normal answer.
FREE = AiAxisProposal(
    name="jpeg_noise",
    definition="8x8 block edges and mosquito noise; 0 = none visible, 100 = heavy",
    scale="0-100",
    direction="higher-is-better",
)


def _item(name: str, mtime: int = 1, **metrics) -> SimpleNamespace:
    return SimpleNamespace(
        path=Path(f"/gallery/{name}"), mtime_ns=int(mtime), metrics=dict(metrics)
    )


def _free_reply(**overrides) -> str:
    row = {
        "name": "jpeg_noise",
        "definition": FREE.definition,
        "scale": "0-100",
        "direction": "higher-is-better",
    }
    row.update(overrides)
    import json

    return json.dumps({"axes": [row]})


# ---------------------------------------------------------------------------
# (a) the selector prompt: EXAMPLES + 3..8 free axes, never a closed list
# ---------------------------------------------------------------------------


def test_selector_prompt_shows_examples_with_meanings_not_a_menu():
    probes = [_item("a.png"), _item("b.png")]
    payload = profile_ai.build_profile_request(
        probes, model="m", salience=salience_summary(probes)
    )
    text = payload["messages"][0]["content"][0]["text"]

    assert "ONLY from this list" not in text, (
        "the closed-menu instruction is withdrawn (owner revision 2026-10-22)"
    )
    assert "EXAMPLES" in text and "NOT A MENU" in text
    assert "not obliged" in text, "the examples must be optional in so many words"
    examples = profile_ai.AXIS_EXAMPLES
    assert len(examples) >= 5
    for name, meaning in examples:
        assert name in text, f"example axis {name!r} is missing from the prompt"
        assert meaning in text, (
            f"the example {name!r} must say WHAT it means — the examples exist to "
            "show the shape of an axis, not to be picked from a list"
        )
    lowered = text.lower()
    assert "from 3 to 8" in lowered, "the owner's 3..8 free-form rule must be stated"
    assert "most differentiate" in lowered
    # The salience summary stays: it is the concrete "most differentiating" input.
    assert "SALIENCE SUMMARY" in text and "members=" in text


def test_selector_prompt_keeps_the_json_contract():
    payload = profile_ai.build_profile_request(
        [_item("a.png")], model="m", salience={}
    )
    text = payload["messages"][0]["content"][0]["text"]
    assert payload["response_format"] == {"type": "json_object"}
    assert "definition" in text and "direction" in text and "0-100" in text
    assert "ONLY a JSON object" in text


# ---------------------------------------------------------------------------
# (b) a free axis survives as a first-class entry (the filter is gone)
# ---------------------------------------------------------------------------


def test_a_free_axis_survives_as_a_first_class_entry():
    profile = parse_profile_reply(_free_reply(), mode="camera")

    assert profile is not None, (
        "a named axis WITH a definition is the normal answer — dropping it (and "
        "falling back to the heuristic) is the defect this wave removes"
    )
    assert profile.source == "vlm" and profile.mode == "camera"
    entries = profile.axis_entries
    assert [entry.name for entry in entries] == ["jpeg_noise"]
    entry = entries[0]
    assert entry.definition == FREE.definition
    assert entry.scale == "0-100"
    assert entry.direction == "higher-is-better"
    assert entry.producer == "vlm" and entry.kind == "candidate"
    assert entry.score == -1, "an axis is chosen before any card is scored"
    assert bool(profile) is True, "a free-only profile is a usable profile"
    assert len(profile) == len(profile.axis_ids) + len(entries)
    assert "jpeg_noise" in profile


def test_the_mode_filter_no_longer_drops_a_pool_id_this_context_cannot_measure():
    assert "ssim" in MEASURED_POOL
    assert "ssim" not in profile_for_mode("camera").axis_ids

    profile = parse_profile_reply('{"axes": ["ssim"]}', mode="camera")

    assert profile is not None, (
        "the mode-availability intersection is withdrawn — a registry id the "
        "judge asked for is kept (the judge measures what no detector can)"
    )
    assert profile.axis_ids == ("ssim",)


def test_a_bare_name_without_a_definition_is_still_refused():
    profile = parse_profile_reply('{"axes": ["made_up"]}', mode="camera")
    assert profile is None, (
        "a bare name carries no meaning and cannot be measured — it is refused, "
        "not stored as a free axis"
    )
    choices = parse_axis_choices(["made_up"])
    assert choices.registry_ids == () and choices.entries == ()
    assert dict(choices.refusals)["made_up"] == REJECT_DEFINITION


def test_a_named_registry_axis_is_that_registry_axis_not_a_duplicate():
    profile = parse_profile_reply(
        '{"axes": [{"name": "noise", '
        '"definition": "grain amplitude; 0 = clean, 100 = heavy", '
        '"scale": "0-100"}]}',
        mode="camera",
    )
    assert profile is not None
    assert profile.axis_ids == ("noise",), "a registry id is the measured axis"
    assert profile.axis_entries == (), "it must not be stored twice"


def test_the_choice_set_caps_at_eight_and_keeps_the_first_occurrence():
    rows = [
        {
            "name": f"axis_{index}",
            "definition": "a dimension that moves between zero and one hundred",
            "scale": "0-100",
        }
        for index in range(AXIS_CHOICE_MAX + 2)
    ]
    rows.append(dict(rows[0]))
    choices = parse_axis_choices(rows)

    assert len(choices.entries) == AXIS_CHOICE_MAX
    reasons = dict(choices.refusals)
    assert reasons["axis_0"] == REJECT_REPEAT
    assert reasons[f"axis_{AXIS_CHOICE_MAX}"] == "over-limit"


def test_a_definition_saying_zero_is_better_flips_the_direction():
    profile = parse_profile_reply(
        '{"axes": [{"name": "invented_detail", '
        '"definition": "made-up texture; 0 = none invented, 100 = fully invented", '
        '"scale": "0-100"}]}',
        mode="camera",
    )
    assert profile is not None
    assert profile.axis_entries[0].direction == "lower-is-better"


# ---------------------------------------------------------------------------
# (c) an unmeasurable proposal is still refused WITH its reason
# ---------------------------------------------------------------------------


def test_a_proposal_with_no_definition_is_refused_with_its_reason():
    entry = {"name": "vibes", "definition": "", "scale": "0-100", "score": 50}
    assert refusal_reason(entry) == REJECT_DEFINITION

    accepted, refusals = parse_proposals(
        [
            entry,
            {
                "name": "halation",
                "definition": "edge crispness; 0 = soft, 100 = fully crisp",
                "scale": "0-100",
                "score": 61,
            },
        ]
    )
    assert [p.name for p in accepted] == ["halation"]
    assert dict(refusals)["vibes"] == REJECT_DEFINITION
    assert accepted[0].direction == "higher-is-better", (
        "the owner rule: higher is better unless the definition says otherwise"
    )


def test_a_proposal_whose_definition_names_zero_as_the_good_end_is_lower_is_better():
    accepted, _refusals = parse_proposals(
        [
            {
                "name": "halation",
                "definition": "a glow bleeding past bright edges; 0 = none, 100 = strong",
                "scale": "0-100",
                "score": 61,
            }
        ]
    )
    assert [p.name for p in accepted] == ["halation"]
    assert accepted[0].direction == "lower-is-better", (
        "a defect axis is not silently read as 'more is better' by the ranker"
    )


# ---------------------------------------------------------------------------
# (d) the scorecard asks for exactly the chosen axes, by name + definition
# ---------------------------------------------------------------------------


def _mixed_profile() -> MetricProfile:
    return MetricProfile(
        axis_ids=("noise",),
        mode="camera",
        source="vlm",
        axis_entries=(FREE,),
    )


def test_the_scorecard_prompt_names_the_chosen_free_axis_with_its_definition():
    from tabs.image_gallery.services.metric_scores import spec_for

    profile = _mixed_profile()
    axes = _scorecard_axes("camera", profile=profile)

    assert ("noise", spec_for("noise").label) in axes, (
        "the registry half keeps its registry label"
    )
    assert ("jpeg_noise", FREE.definition) in axes, (
        "a free axis reaches the model as a NAME + its definition, so it can be "
        f"measured instead of guessed; got {axes}"
    )

    text = build_prompt("camera", profile=profile)
    assert '"jpeg_noise"' in text
    assert FREE.definition in text
    assert '"noise"' in text, "the registry axes keep their current behaviour"
    assert "0-100" in text


def test_a_free_only_profile_asks_for_its_own_axes_not_the_mode_mapping():
    profile = MetricProfile(mode="camera", source="vlm", axis_entries=(FREE,))
    axes = _scorecard_axes("camera", profile=profile)
    assert axes == (("jpeg_noise", FREE.definition),), (
        "when the judge named only its own axes, the mode mapping is not its set"
    )


def test_without_a_profile_the_scorecard_is_byte_identical():
    for mode in ("camera", "fidelity", "batch_synthetic", None):
        assert build_prompt(mode) == build_prompt(mode, profile=None)


def test_a_registry_only_profile_prompt_is_byte_identical_to_the_mode_mapping():
    mode_only = build_prompt("camera")
    registry = MetricProfile(
        axis_ids=profile_for_mode("camera").axis_ids, mode="camera", source="vlm"
    )
    assert build_prompt("camera", profile=registry) == mode_only, (
        "no judge axes → the scorecard asks the same question it always did, so "
        "existing cached scorecards stay readable"
    )
    assert "score exactly that scale" not in mode_only


def test_a_judge_axis_makes_the_scale_explicit():
    text = build_prompt("camera", profile=_mixed_profile())
    assert "score exactly that scale" in text, (
        "a free axis' definition fixes its own 0..100 meaning — the prompt must "
        "not let the model re-read it as '100 = best'"
    )


# ---------------------------------------------------------------------------
# (e) the registry half still resolves for the local rows / fusion
# ---------------------------------------------------------------------------


def test_a_profile_with_a_free_axis_still_resolves_the_registry_part():
    profile = _mixed_profile()
    assert measured_axes_for("camera", profile=profile) == ("noise",), (
        "measured_axes_for is the REGISTRY half — the local rows and the fusion "
        "keep reading real detector ids"
    )
    assert "jpeg_noise" not in measured_axes_for("camera", profile=profile)


# ---------------------------------------------------------------------------
# extra seams: pin, cache identity, usability, provenance
# ---------------------------------------------------------------------------


def test_the_pin_round_trips_the_judged_entries(tmp_path):
    cache = ProfileCache(tmp_path)
    profile = MetricProfile(
        axis_ids=("noise",), mode="camera", source="vlm", axis_entries=(FREE,)
    )
    cache.put("k", profile)
    assert cache.get("k") == profile, "a cached selection must equal the fresh one"


def test_a_free_only_profile_is_pinned_and_served(tmp_path):
    cache = ProfileCache(tmp_path)
    profile = MetricProfile(mode="camera", source="vlm", axis_entries=(FREE,))
    cache.put("k", profile)
    stored = cache.get("k")
    assert stored is not None, "a free-only selection is not an empty selection"
    assert [entry.name for entry in stored.axis_entries] == ["jpeg_noise"]


def test_the_analyze_identity_covers_the_judge_axes():
    baseline = analysis_cache_identity(
        None, mode="camera", profile=MetricProfile(axis_ids=("noise",), mode="camera")
    )
    with_free = analysis_cache_identity(
        None, mode="camera", profile=_mixed_profile()
    )
    other_definition = analysis_cache_identity(
        None,
        mode="camera",
        profile=MetricProfile(
            axis_ids=("noise",),
            mode="camera",
            axis_entries=(
                AiAxisProposal(name="jpeg_noise", definition="a different axis"),
            ),
        ),
    )
    assert with_free["profile"] != baseline["profile"], (
        "the axis set is part of the identity: a different question cannot serve "
        "the previous scorecard"
    )
    assert other_definition["profile"] != with_free["profile"], (
        "the definition is part of the prompt, so it is part of the identity"
    )
    assert baseline["profile"] == "noise", "a registry-only identity is unchanged"


def test_active_profile_keeps_a_free_only_answer():
    profile = MetricProfile(mode="camera", source="vlm", axis_entries=(FREE,))
    state = SimpleNamespace(metric_profile=profile, mode="camera")
    assert active_profile(state) is profile, (
        "the accessor must not discard a judge answer that names only its own axes"
    )


class _Owner:
    """Qt-free double binding the REAL ``_apply_profile_outcome``."""

    def __init__(self, profile) -> None:
        self.state = SimpleNamespace(
            items=[GalleryItem(path=Path("/gallery/one.png"), mtime_ns=0)],
            mode="camera",
            metric_profile=profile,
            profile_reject_reason="",
        )
        self._judgment_domain = "ai"
        self._folder_gen = 0
        self._profile_consumed_gen = None
        self.refreshed: list = []
        self.widget = SimpleNamespace(refresh_cards=self.refreshed.extend)

    def _is_current_folder_gen(self, gen) -> bool:
        return GalleryController._is_current_folder_gen(self, gen)

    def _apply_profile_outcome(self, profile, gen) -> None:
        GalleryController._apply_profile_outcome(self, profile, gen)

    def _tr(self, key: str, default: str) -> str:
        return default


def test_a_free_only_answer_is_applied_not_rejected_as_hollow():
    heuristic = profile_for_mode("camera")
    owner = _Owner(heuristic)
    free_only = MetricProfile(mode="camera", source="vlm", axis_entries=(FREE,))

    owner._apply_profile_outcome(free_only, 0)

    assert owner.state.metric_profile is free_only, (
        "a judge answer made only of its own axes is a complete profile — "
        f"rejected as {owner.state.profile_reject_reason!r}"
    )
    assert owner.state.profile_reject_reason == ""
    assert owner.refreshed, "the cards are refreshed like the neighbouring apply-tails"

    # End to end through the seam the analyze path reads: the stored profile is
    # what the scorecard is built from, and it asks for the judge's axis by name.
    prompt = build_prompt(owner.state.mode, profile=owner.state.metric_profile)
    assert '"jpeg_noise"' in prompt and FREE.definition in prompt


def test_a_cached_scorecard_keeps_the_proposal_direction(tmp_path, monkeypatch):
    from tabs.image_gallery.models import AiAnalysisResult
    from tabs.image_gallery.services import ai_cache

    monkeypatch.setattr(ai_cache, "ai_cache_dir", lambda: tmp_path)
    identity = ai_cache.analysis_cache_identity(
        None, mode="camera", profile=("noise",)
    )
    path = Path("/gallery/one.png")
    result = AiAnalysisResult(
        description="",
        tags=(),
        model="m",
        analyzed_at_iso="t",
        axes={"noise": 80},
        axis_proposals=(
            AiAxisProposal(
                name="invented_detail",
                definition="made-up texture; 0 = none, 100 = fully invented",
                score=62,
                direction="lower-is-better",
            ),
        ),
    )
    ai_cache.save_analysis(path, 1, result, identity)

    loaded = ai_cache.load_cached_analysis(path, 1, identity)

    assert loaded is not None
    assert [p.name for p in loaded.axis_proposals] == ["invented_detail"]
    assert loaded.axis_proposals[0].direction == "lower-is-better", (
        "a HIT must not hand the ranker a different axis than a MISS would"
    )


def test_provenance_labels_the_two_halves_and_never_guesses():
    profile = _mixed_profile()
    assert axis_provenance("jpeg_noise", profile=profile) == PROVENANCE_JUDGE
    assert axis_provenance("noise", profile=profile) == PROVENANCE_LOCAL
    # A reference axis has no local producer in a camera folder: if the judge
    # asked for it, only the judge can measure it.
    asked_unavailable = MetricProfile(
        axis_ids=("ssim",), mode="camera", source="vlm", axis_entries=(FREE,)
    )
    assert (
        axis_provenance("ssim", mode="camera", profile=asked_unavailable)
        == PROVENANCE_JUDGE
    )
    assert axis_provenance("unheard_of", profile=profile) == ""


def test_the_trace_line_names_the_judged_axes_and_their_direction():
    line = format_profile(_mixed_profile())
    assert "axes=noise" in line and "source=vlm" in line
    assert "judged=jpeg_noise~higher-is-better" in line, (
        f"the trace must show the judge half separately; got {line!r}"
    )


@pytest.mark.parametrize("mode", ["camera", "fidelity", "batch_synthetic"])
def test_a_plain_registry_profile_is_unchanged(mode):
    profile = MetricProfile(axis_ids=("noise", "sharpness"), mode=mode, source="vlm")
    assert profile.axis_entries == ()
    assert measured_axes_for(mode, profile=profile) == ("sharpness", "noise")
    assert [axis for axis, _label in _scorecard_axes(mode, profile=profile)] == [
        "sharpness",
        "noise",
    ]
