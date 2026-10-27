"""P7-A — the judge NAMES the axes (plan-gallery-ai-judgement §OWNER REVISION 2026-10-22).

The owner replaced the "choose from the pool" design: the VLM is shown EXAMPLES of
what an axis can be (not a menu), asked for **5..8 axes in free form** that most
differentiate THESE pictures, and an axis it names is a first-class entry (name +
definition + scale + direction), not a registry id it had to guess.

Falsification story (what each test would catch, and why it is red before):

- **(a)** the selector prompt offers examples-with-meanings and the 5..8 free-form
  instruction. Red before: the text opened with ``METRIC POOL — choose axis ids
  ONLY from this list`` and asked for ``{"axes": ["<id>", ...]}``.
- **(b)** an axis whose name is NOT in ``MEASURED_POOL`` and NOT in
  ``profile_for_mode(mode).axis_ids`` SURVIVES as a first-class entry — with its
  definition, its scale and its direction. Red before: ``parse_profile_reply``
  intersected the answer with the mode's axis set, so the name was dropped and the
  reply degraded to the heuristic (``MetricProfile`` could not carry an entry at
  all). The same test covers the registry id the mode cannot measure (``ssim`` in
  a camera folder): the filter is gone, the id stays.
- **(c)** a proposal that carries no definition is KEPT with ``definition=""``
  and the ``no-definition`` audit code — the definition is metadata since the
  owner rule of 2026-10-27; what is still refused is structure (an unusable name,
  a pool duplicate, a repeat, an unsupported scale, a missing score).
- **(d)** the scorecard prompt asks for the chosen free axis BY NAME with its
  definition, and for the registry axes exactly as before.
- **(e)** a profile carrying a free axis still resolves ``measured_axes_for()`` for
  its registry part (the local rows/fusion keep reading real detector ids).

Red-before evidence for every one of these was produced on a pre-change scratch
copy of ``HEAD`` (``git archive HEAD``) — see ``DONE.md``.

Owner rule 2026-10-27 (verbatim): *"we must not decide what is measurable and
what is not. If the app said it needs such metrics, we draw them, period."* The
model's answer is therefore kept unless its STRUCTURE is unusable — a bare string
name and an object are the same axis, a missing/short definition is metadata
(``definition=""`` + the ``no-definition`` audit code), and a non-English
definition is not "empty". Tests (f) below pin exactly that inversion.

Extra seams the same wave has to keep honest: the pin round-trips entries (a
re-open must not re-roll the judge's axes), the analyze cache identity covers the
judge's axes (a different question cannot serve an old scorecard), a free-only
answer is a USABLE profile (not "hollow"), and the two provenances stay labelled.
"""

from __future__ import annotations

import json
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
    AUDIT_NO_DEFINITION,
    REJECT_NAME,
    REJECT_REPEAT,
    definition_audit,
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
#: The examples list the selector prompt used to carry (owner order 2026-10-26:
#: DELETE it). The pairs are kept here ONLY as a regression guard — the prompt
#: may never name them again; nothing reads them as a vocabulary.
RETIRED_EXAMPLES: tuple[tuple[str, str], ...] = (
    ("clarity", "how clean the picture reads"),
    ("hallucination", "detail the processing invented"),
    ("banding", "stepped tone transitions"),
    ("white_balance", "a colour cast that pushes every neutral"),
    ("jpeg_noise", "8x8 block edges and mosquito noise"),
    ("halation", "a red or orange glow bleeding past bright edges"),
    ("posterization", "tones flattened into visible bands"),
)

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
    return json.dumps({"axes": [row]})


def _settings(**overrides) -> SimpleNamespace:
    """An AI settings row that passes ``ai_selector_available``."""
    base = {
        "enabled": True,
        "api_key": "k",
        "base_url": "http://x",
        "model": "m",
        "reasoning_effort": "auto",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _chat(axes) -> dict:
    """A chat envelope carrying ``{"axes": <axes>}``."""
    return {"choices": [{"message": {"content": json.dumps({"axes": axes})}}]}


@pytest.fixture
def _stub_image_encoding(monkeypatch):
    from tabs.image_gallery.services import vlm

    monkeypatch.setattr(vlm, "_encode_image", lambda path: ("png", "QUJD"))


def _choose(items, reply, *, calls, cache):
    """Run the REAL selector with an injected transport that always answers *reply*."""

    def _client(base_url, api_key, payload):
        calls.append(payload)
        return reply

    from tabs.image_gallery.use_cases.profile_ai import choose_profile_sync

    return choose_profile_sync(
        items,
        mode="camera",
        settings=_settings(),
        cache=cache,
        client_call=_client,
    )



# ---------------------------------------------------------------------------
# (a) the selector prompt: EXAMPLES + 5..8 free axes, never a closed list
# ---------------------------------------------------------------------------


def test_selector_prompt_names_no_axis_of_its_own_and_leads_with_evidence():
    """Inverted on purpose by ``task-profile-granularity`` (2026-10-26).

    The examples list ("clarity", "hallucination", "banding", …) is DELETED: a
    labelled menu is what the model anchored on, so the paid answer was a guess
    wearing the prompt's own words. The request now carries the measured evidence
    of THIS series (per-axis spread + per-probe scores) and the schema — which is
    also the cheapest guard against the examples creeping back.
    """
    probes = [
        SimpleNamespace(path=Path("/gallery/a.png"), mtime_ns=1, metrics={"sharpness": 40.0}),
        SimpleNamespace(path=Path("/gallery/b.png"), mtime_ns=1, metrics={"sharpness": 80.0}),
    ]
    summary = salience_summary(probes, probes=probes)
    payload = profile_ai.build_profile_request(probes, model="m", salience=summary)
    text = payload["messages"][0]["content"][0]["text"]

    assert "ONLY from this list" not in text, "the closed menu stays withdrawn"
    assert "EXAMPLES of what an axis can be" not in text, (
        "the examples list is DELETED — the prompt may not name an axis of its own"
    )
    for name, meaning in RETIRED_EXAMPLES:
        assert name not in text, f"retired example axis {name!r} is back in the prompt"
        assert meaning not in text, f"the retired example {name!r} came back with its meaning"
    assert "EVIDENCE" in text, "the measured evidence is the request's ground truth"
    assert "spread" in text and "sharpness" in text, (
        "the per-axis measured differences of THIS series travel with the images"
    )
    assert "each attached image" in text, (
        "the per-probe scores are what lets an axis be tied to a visible difference"
    )
    lowered = text.lower()
    assert "from 5 to 8" in lowered, "the owner's 5..8 free-form rule must be stated"
    assert "most differentiate" in lowered
    assert "why" in lowered, "every axis must be tied to an observed difference"


def test_selector_prompt_keeps_the_json_contract():
    payload = profile_ai.build_profile_request(
        [_item("a.png")], model="m", salience={}
    )
    text = payload["messages"][0]["content"][0]["text"]
    assert payload["response_format"] == {"type": "json_object"}
    assert "definition" in text and "direction" in text and "0-100" in text
    assert "ONLY a JSON object" in text
    # Owner 2026-10-27: the axis is DRAWN under the model's own human name, so
    # the selector (the path that named the owner's six axes) must ASK for it.
    assert '"label"' in text, "the selector contract must request a human label"


def test_a_selector_label_reaches_the_profile_entry():
    """The selector's human label survives into the entry (row header source).

    Owner 2026-10-27: the rows showed ``line_crispness`` because the contract
    had no name field. The parser already keeps ``label`` when a reply carries
    one; this pins the pair (contract asks, parser stores) for the SELECTOR path.
    """
    from tabs.image_gallery.services.axis_choice import parse_axis_choices

    got = parse_axis_choices(
        [
            {
                "name": "line_crispness",
                "label": "Line crispness",
                "definition": "How cleanly fine lines separate; 0 = mush, 100 = crisp",
                "scale": "0-100",
                "direction": "higher-is-better",
            }
        ]
    )

    assert got.entries, got.refusals
    assert got.entries[0].name == "line_crispness"
    assert got.entries[0].label == "Line crispness"


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


def test_a_bare_name_without_a_definition_is_kept_with_an_audit_code():
    """Owner rule 2026-10-27: the FORM of the answer decides nothing.

    A bare string name is the terse shape of the same free axis, so it is stored
    with ``definition=""`` and the ``no-definition`` audit code, and the scorecard
    asks for it by name. Red before: ``parse_axis_choices`` refused every bare
    name outside the pool with ``REJECT_DEFINITION`` and the reply fell back.
    """
    profile = parse_profile_reply('{"axes": ["glow_bloom"]}', mode="camera")

    assert profile is not None, (
        "a name the model gave is an axis — the app never decides whether it is "
        "measurable"
    )
    assert profile.source == "vlm"
    assert [entry.name for entry in profile.axis_entries] == ["glow_bloom"]
    assert profile.axis_entries[0].definition == "", "no definition was given"
    assert bool(profile) is True, "a free-only profile is a usable profile"

    choices = parse_axis_choices(["glow_bloom"])
    assert choices.registry_ids == ()
    assert [entry.name for entry in choices.entries] == ["glow_bloom"]
    assert choices.refusals == (), "a bare name is not a structural refusal"
    assert dict(choices.audits)["glow_bloom"] == AUDIT_NO_DEFINITION

    axes = _scorecard_axes("camera", profile=profile)
    assert ("glow_bloom", "glow_bloom") in axes, (
        f"the scorecard must ask for the axis the judge named; got {axes}"
    )
    assert '"glow_bloom"' in build_prompt("camera", profile=profile)


def test_a_string_and_an_object_are_the_same_axis():
    """The form must not decide legality: same name ⇒ same profile, byte for byte."""
    as_string = parse_profile_reply('{"axes": ["glow_bloom"]}', mode="camera")
    as_object = parse_profile_reply(
        '{"axes": [{"name": "glow_bloom", "definition": "", "scale": "0-100"}]}',
        mode="camera",
    )

    assert as_string is not None and as_object is not None
    assert as_string == as_object, (
        "a bare name and an object naming the same axis must produce the same "
        f"profile; got {as_string} vs {as_object}"
    )
    assert as_string.axis_entries[0].definition == ""


def test_a_russian_definition_is_kept():
    """The deleted English whitelist dropped every non-English definition."""
    russian = "мягкое свечение вокруг ярких краёв; 0 = нет, 100 = сильное"
    entry = {"name": "glow_bloom", "definition": russian, "scale": "0-100", "score": 44}

    assert refusal_reason(entry) == "", (
        "a definition the model wrote in its own language is a definition"
    )
    accepted, refusals = parse_proposals([entry])
    assert [p.name for p in accepted] == ["glow_bloom"]
    assert accepted[0].definition == russian, "the meaning travels untouched"
    assert refusals == ()

    profile = parse_profile_reply(
        json.dumps({"axes": [{"name": "glow_bloom", "definition": russian, "scale": "0-100"}]}),
        mode="camera",
    )
    assert profile is not None
    assert profile.axis_entries[0].definition == russian


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


def test_a_proposal_with_no_definition_is_kept_with_an_audit_code():
    """The definition is metadata: the axis survives, the gap is recorded."""
    entry = {"name": "vibes", "definition": "", "scale": "0-100", "score": 50}
    assert refusal_reason(entry) == "", "a missing definition is not a refusal"
    assert definition_audit("") == AUDIT_NO_DEFINITION

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
    assert [p.name for p in accepted] == ["vibes", "halation"], (
        "the store keeps a definition-less axis instead of dropping it"
    )
    assert accepted[0].definition == ""
    assert accepted[0].score == 50, "its reading is what makes it usable"
    assert refusals == (), "nothing was refused — only audited"
    assert accepted[1].direction == "higher-is-better", (
        "the owner rule: higher is better unless the definition says otherwise"
    )


def test_a_proposal_with_an_unusable_name_is_still_refused():
    """Structure keeps its refusals: a phrase is not an axis."""
    accepted, refusals = parse_proposals(
        [{"name": "!!!", "definition": "", "scale": "0-100", "score": 50}]
    )
    assert accepted == ()
    assert dict(refusals)["#1"] == REJECT_NAME


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


def test_the_profiles_own_axes_are_the_rank_set_registry_then_judged():
    """Inverted on purpose by ``task-profile-granularity`` (2026-10-26).

    ``measured_axes_for`` used to return the registry half only, so a profile of
    ``axes=noise`` + ``judged=jpeg_noise`` ranked on noise ALONE while the paid
    axis only labelled cards. Owner design: the axis set is the ACTIVE PROFILE'S
    OWN list — registry ids then the judge's free names, no registry
    reconciliation.
    """
    profile = _mixed_profile()
    assert measured_axes_for("camera", profile=profile) == ("noise", "jpeg_noise"), (
        "a judge-named axis is first-class: it carries the per-card numbers and it "
        "ranks"
    )
    # …and the mode mapping is still the fallback for an absent profile.
    assert "jpeg_noise" not in measured_axes_for("camera", profile=None)


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


def test_the_analyze_identity_records_the_judge_axes_without_keying_them():
    """Inverted on purpose by ``task-analysis-phase-state`` (2026-10-26).

    The axis set used to be part of the KEY, so a re-rolled profile was a MISS for
    every card (measured 3 HIT / 7 MISS on 10 images whose entries were all on
    disk). The identity now names the backend/mode/sampling/prompt revision and
    RECORDS the axis set under ``"profile"``: the record still distinguishes the
    questions (a different axis, a redefined one), the key does not.
    """
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
    key_fields = ("model", "base_url", "reasoning_effort", "k",
                  "effective_k", "temperature", "seed", "prompt_schema_version")
    assert {k: with_free[k] for k in key_fields} == {
        k: baseline[k] for k in key_fields
    }, (
        "the axis set must not reach the KEY: that is what re-analyzed the folder "
        "on every profile re-roll"
    )
    assert with_free["profile"] != baseline["profile"], (
        "the entry still RECORDS which question it answered (registry axes + the "
        "judge's own names)"
    )
    assert (
        other_definition["profile"]["definitions"]
        != with_free["profile"]["definitions"]
    ), "the definition travels in the record, so a redefined axis is visible"
    assert baseline["profile"] == {
        "axes": ["noise"],
        "judged": [],
        "definitions": {},
        "source": "heuristic",
        "mode": "camera",
    }, "a registry-only identity records exactly its axes"


def test_active_profile_keeps_a_free_only_answer():
    profile = MetricProfile(mode="camera", source="vlm", axis_entries=(FREE,))
    state = SimpleNamespace(ai_profile=profile, mode="camera")
    assert active_profile(state, domain="ai") is profile, (
        "the accessor must not discard a judge answer that names only its own axes"
    )


class _Owner:
    """Qt-free double binding the REAL ``_apply_profile_outcome``."""

    def __init__(self, profile) -> None:
        self.state = SimpleNamespace(
            items=[GalleryItem(path=Path("/gallery/one.png"), mtime_ns=0)],
            mode="camera",
            algorithms_profile=profile,
            ai_profile=None,
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

    assert owner.state.ai_profile is free_only, (
        "a judge answer made only of its own axes is a complete profile — "
        f"rejected as {owner.state.profile_reject_reason!r}"
    )
    assert owner.state.algorithms_profile == heuristic, (
        "the AI answer must not overwrite the Algorithms backend's own slot"
    )
    assert owner.state.profile_reject_reason == ""
    assert owner.refreshed, "the cards are refreshed like the neighbouring apply-tails"

    # End to end through the seam the analyze path reads: the stored profile is
    # what the scorecard is built from, and it asks for the judge's axis by name.
    prompt = build_prompt(owner.state.mode, profile=owner.state.ai_profile)
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


# ---------------------------------------------------------------------------
# (f) the owner rule 2026-10-27: the KEPT count decides, never the refusals
# ---------------------------------------------------------------------------


def test_a_full_answer_with_five_free_names_is_not_retried(tmp_path, _stub_image_encoding):
    """8 axes named, 5 of them free names with no definition — a COMPLETE answer.

    Red before: every bare name outside the pool was refused, so the profile kept
    3 registry ids, the 5..8 gate called the answer "thin", ONE retry was paid and
    the run fell back — a full paid answer turned into a failure by the parser.
    """
    items = [_item("a.png", sharpness=0.0), _item("b.png", sharpness=400.0)]
    calls: list = []
    reply = _chat(
        [
            "sharpness",
            "noise",
            "exposure",
            "glow_bloom",
            "halation_bleed",
            "tone_flattening",
            "chroma_drift",
            "veil_haze",
        ]
    )

    profile = _choose(items, reply, calls=calls, cache=ProfileCache(tmp_path))

    assert len(calls) == 1, (
        f"a full answer must not be retried (calls={len(calls)}): refusals cannot "
        "turn kept axes into a thin answer"
    )
    assert profile is not None and profile.source == "vlm", (
        "the answer is applied, not replaced by the local offer"
    )
    assert len(profile.axis_ids) + len(profile.axis_entries) == 8
    assert {entry.name for entry in profile.axis_entries} == {
        "glow_bloom",
        "halation_bleed",
        "tone_flattening",
        "chroma_drift",
        "veil_haze",
    }
    assert all(entry.definition == "" for entry in profile.axis_entries), (
        "none of the free names carried a definition — that is metadata, not a loss"
    )
    assert _scorecard_axes("camera", profile=profile)[-1][0] == "veil_haze", (
        "the scorecard asks for the judge's own axes in the model's order"
    )


def test_three_kept_axes_are_not_a_thin_answer(tmp_path, _stub_image_encoding):
    """The owner's rule is 3..8, counted over KEPT axes — 3 is complete enough."""
    items = [_item("a.png", sharpness=0.0), _item("b.png", sharpness=400.0)]
    calls: list = []

    profile = _choose(
        items, _chat(["glow_bloom", "halation_bleed", "veil_haze"]),
        calls=calls, cache=ProfileCache(tmp_path),
    )

    assert len(calls) == 1, "three kept axes are not retried"
    assert profile is not None
    assert [entry.name for entry in profile.axis_entries] == [
        "glow_bloom",
        "halation_bleed",
        "veil_haze",
    ]


def test_a_repeat_inside_one_reply_still_costs_exactly_that_axis(
    tmp_path, _stub_image_encoding, caplog
):
    """Structure keeps its refusals — and a refusal does not un-keep the rest."""
    import logging

    from core.log_names import APP_LOGGER_NAME

    items = [_item("a.png", sharpness=0.0), _item("b.png", sharpness=400.0)]
    calls: list = []
    reply = _chat(["glow_bloom", "glow_bloom", "halation_bleed", "veil_haze"])

    with caplog.at_level(logging.DEBUG, logger=APP_LOGGER_NAME):
        profile = _choose(items, reply, calls=calls, cache=ProfileCache(tmp_path))

    assert len(calls) == 1
    assert [entry.name for entry in profile.axis_entries] == [
        "glow_bloom",
        "halation_bleed",
        "veil_haze",
    ]
    assert any(
        "glow_bloom=repeated-axis" in record.getMessage() for record in caplog.records
    ), "the refused repeat is recorded, never silent"


def test_a_bare_name_carries_its_audit_code_into_the_profile(
    tmp_path, _stub_image_encoding
):
    """The audit code is not lost on the way into ``MetricProfile``."""
    from tabs.image_gallery.services.metric_profile import MetricProfile

    profile = MetricProfile(
        mode="camera",
        source="vlm",
        axis_entries=(AiAxisProposal(name="glow_bloom"),),
    )
    assert [entry.name for entry in profile.axis_entries] == ["glow_bloom"], (
        "an entry whose definition is empty must survive profile normalization"
    )
    assert profile.axis_entries[0].definition == ""

    items = [_item("a.png", sharpness=0.0), _item("b.png", sharpness=400.0)]
    calls: list = []
    chosen = _choose(
        items, _chat(["glow_bloom", "halation_bleed", "veil_haze"]),
        calls=calls, cache=ProfileCache(tmp_path),
    )
    assert chosen == MetricProfile(
        mode="camera",
        source="vlm",
        axis_entries=(
            AiAxisProposal(name="glow_bloom"),
            AiAxisProposal(name="halation_bleed"),
            AiAxisProposal(name="veil_haze"),
        ),
    )
