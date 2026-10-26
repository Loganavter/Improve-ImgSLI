"""P3 — the profile's own axes RANK, 3..8 is enforced, one profile per SERIES.

``task-profile-granularity-and-axis-reporting`` (2026-10-26). Measured defects:

- **the judge-named axes never ranked**: ``rank_fusion.measured_axes_for(profile)``
  returned only ``profile.axis_ids``, so a profile of ``axes=sharpness`` +
  ``judged=contrast,color_saturation,grain`` ranked on sharpness ALONE while three
  paid axes only labelled cards;
- **the "3 to 8" rule was advisory**: a 1-axis reply was accepted, so a whole
  folder was ordered on one axis;
- **one profile per folder**, chosen from ``adaptive_k`` probes, applied to every
  series although the plan is folder → SERIES → domain;
- the prompt carried an examples MENU of concrete axis names, which the model
  anchored on instead of the evidence (owner order 2026-10-26: DELETE it, put the
  measured evidence first, require a ``why`` per axis, and never spend a call
  when there is no evidence to anchor on).

Falsification story (each test names the defect it kills):

- **a** — two cards identical on every registry axis and opposite on one
  judge-named axis order by that axis. Red before: the judge axis had no weight.
- **b** — a profile whose names match NO registry id still ranks. Red before:
  ``measured_axes_for`` answered from the registry half and the profile fell back
  to the mode mapping.
- **c** — a 1-axis reply is retried ONCE and then refused with a WARN + the
  series offer. Red before: it was accepted silently.
- **d** — a multi-group folder resolves and LOGS one profile per series (the
  folder answer is the seed). Red before: one folder-wide set for every series.
- **e** — an axis with an empty ``why`` is retried, then refused with a WARN.
- **f** — no measured evidence ⇒ ZERO profile requests (WARN + offer). Red
  before: the call was made and the answer anchored on the examples.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from tabs.image_gallery.controller import GalleryController
from tabs.image_gallery.models import AiAnalysisResult, AiAxisProposal, GalleryItem
from tabs.image_gallery.services.metric_profile import MetricProfile, profile_for_mode
from tabs.image_gallery.services.profile_cache import ProfileCache
from tabs.image_gallery.services.rank_fusion import (
    item_quality,
    measured_axes_for,
    rank_series,
)
from tabs.image_gallery.use_cases import profile_probe
from tabs.image_gallery.use_cases.profile_ai import (
    axis_count_report,
    choose_profile_sync,
    per_series_profiles,
)
from core.log_names import APP_LOGGER_NAME

SETTINGS = SimpleNamespace(
    enabled=True,
    api_key="k",
    base_url="https://openrouter.ai/api/v1",
    model="m",
    reasoning_effort="auto",
)

#: Axes the judge named — neither is a registry id, which is the point.
JUDGED_A = AiAxisProposal(
    name="banding",
    definition="stepped tone transitions; 0 = none, 100 = heavy",
    scale="0-100",
    direction="lower-is-better",
)
JUDGED_B = AiAxisProposal(
    name="ringing",
    definition="halo oscillation at edges; 0 = none, 100 = severe",
    scale="0-100",
    direction="lower-is-better",
)


@pytest.fixture(autouse=True)
def _stub_image_encoding(monkeypatch):
    from tabs.image_gallery.services import vlm

    monkeypatch.setattr(vlm, "_encode_image", lambda path: ("png", "QUJD"))


def _card(name: str, *, registry: dict, judged: dict) -> GalleryItem:
    item = GalleryItem(path=Path(f"/gallery/{name}"), mtime_ns=1)
    # Already-scored local numbers (0..100) as engine records: ``metrics`` holds
    # RAW detector values, which ``score_for`` maps, and this test is about which
    # INSTRUMENT an axis reads, not about the mapping.
    item.analysis_records = tuple(
        SimpleNamespace(axis=axis, status="ok", value=float(value))
        for axis, value in registry.items()
    )
    item.analysis = AiAnalysisResult(
        description="",
        tags=(),
        model="m",
        analyzed_at_iso="t",
        axes={**registry, **judged},
    )
    return item


# ---------------------------------------------------------------------------
# (a) the judge-named axes RANK
# ---------------------------------------------------------------------------


def test_two_cards_identical_locally_are_ordered_by_the_judge_axis() -> None:
    profile = MetricProfile(
        axis_ids=("sharpness",),
        mode="camera",
        source="vlm",
        axis_entries=(JUDGED_A,),
    )
    better = _card("better.png", registry={"sharpness": 50}, judged={"banding": 90})
    worse = _card("worse.png", registry={"sharpness": 50}, judged={"banding": 10})

    assert measured_axes_for("camera", profile=profile) == ("sharpness", "banding"), (
        "the profile's own axes ARE the rank set — registry ids then the judge's "
        "names (owner design 2026-10-26)"
    )
    assert item_quality(better, mode="camera", profile=profile) > item_quality(
        worse, mode="camera", profile=profile
    ), "the judge axis must carry weight, not just a label"

    ranks = rank_series([worse, better], mode="camera", profile=profile)
    assert ranks[str(better.path)] == 1 and ranks[str(worse.path)] == 2, (
        "identical on every registry axis and opposite on the judge axis: the "
        "order must follow the judge axis"
    )


def test_a_local_detector_value_wins_for_a_registry_axis() -> None:
    """One axis, one instrument: the scorecard number never overrides a detector."""
    profile = MetricProfile(
        axis_ids=("sharpness",), mode="camera", source="vlm", axis_entries=(JUDGED_A,)
    )
    item = _card("a.png", registry={"sharpness": 50}, judged={"sharpness": 99, "banding": 40})
    quality = item_quality(item, mode="camera", profile=profile)
    assert quality is not None
    # mean(sharpness 50, banding 40) = 45, capped at worst(40) + 20 → 45.
    assert abs(quality - 45.0) < 0.001, (
        "a registry axis keeps its LOCAL number even when the judge also scored it"
    )


# ---------------------------------------------------------------------------
# (b) a free-only profile still ranks (no registry id anywhere)
# ---------------------------------------------------------------------------


def test_a_profile_whose_names_match_no_registry_id_still_ranks() -> None:
    profile = MetricProfile(
        mode="camera", source="vlm", axis_entries=(JUDGED_A, JUDGED_B)
    )
    assert profile.axis_ids == () and len(profile.axis_entries) == 2

    clean = _card("clean.png", registry={}, judged={"banding": 90, "ringing": 85})
    noisy = _card("noisy.png", registry={}, judged={"banding": 20, "ringing": 25})

    assert measured_axes_for("camera", profile=profile) == ("banding", "ringing"), (
        "a free-only profile must not fall back to the mode mapping: its own axes "
        "are the measurement"
    )
    ranks = rank_series([noisy, clean], mode="camera", profile=profile)
    assert ranks[str(clean.path)] == 1 and ranks[str(noisy.path)] == 2


def test_an_axis_with_no_number_is_a_gap_not_a_zero() -> None:
    profile = MetricProfile(
        axis_ids=("sharpness",), mode="camera", source="vlm", axis_entries=(JUDGED_A,)
    )
    scored = _card("scored.png", registry={"sharpness": 50}, judged={"banding": 80})
    gap = _card("gap.png", registry={"sharpness": 50}, judged={})
    assert item_quality(gap, mode="camera", profile=profile) == pytest.approx(50.0), (
        "a missing judge value leaves the axis out of the mean — never 0"
    )
    ranks = rank_series([gap, scored], mode="camera", profile=profile)
    assert sorted(ranks.values()) == [1, 2]
    assert ranks[str(scored.path)] == 1, "the scored card wins on the axis it answered"


# ---------------------------------------------------------------------------
# (c)+(e) the 3..8 and `why` rules: one retry, then WARN + fallback
# ---------------------------------------------------------------------------


def _evidence_items() -> list:
    return [
        SimpleNamespace(
            path=Path("/gallery/a.png"), mtime_ns=1, metrics={"sharpness": 0.0}
        ),
        SimpleNamespace(
            path=Path("/gallery/b.png"), mtime_ns=1, metrics={"sharpness": 400.0}
        ),
    ]


def _reply(rows) -> dict:
    return {"choices": [{"message": {"content": json.dumps({"axes": rows})}}]}


def _three_axes(**overrides) -> list:
    rows = [
        {
            "name": "banding",
            "definition": "stepped tone transitions; 0 = none, 100 = heavy",
            "scale": "0-100",
            "direction": "lower-is-better",
            "why": "the probes differ on stepped gradients",
        },
        {
            "name": "ringing",
            "definition": "halo oscillation at edges; 0 = none, 100 = severe",
            "scale": "0-100",
            "direction": "lower-is-better",
            "why": "the probes differ on edge halos",
        },
        {
            "name": "sharpness",
            "definition": "micro-contrast; 0 = mushy, 100 = crisp",
            "scale": "0-100",
            "direction": "higher-is-better",
            "why": "the measured spread separates the probes",
        },
    ]
    for row in rows:
        row.update(overrides)
    return rows


def test_a_one_axis_reply_is_retried_once_then_warned_and_falls_back(
    tmp_path, caplog
) -> None:
    cache = ProfileCache(tmp_path)
    payloads: list = []

    def _client(base_url, api_key, payload):
        payloads.append(payload)
        return _reply([_three_axes()[0]])  # ONE axis, twice

    with caplog.at_level(logging.WARNING, logger=APP_LOGGER_NAME):
        profile = choose_profile_sync(
            _evidence_items(), mode="camera", settings=SETTINGS, cache=cache,
            client_call=_client,
        )

    assert len(payloads) == 2, "exactly ONE retry for a thin answer"
    assert profile.source != "vlm", "a 1-axis answer may never become the profile"
    warnings = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert any("only 1 axe(s) named" in text for text in warnings), (
        "the refusal must say WHY (the count rule), not disappear into a debug line"
    )


def test_a_three_axis_reply_is_accepted_and_pinned(tmp_path) -> None:
    cache = ProfileCache(tmp_path)
    payloads: list = []

    def _client(base_url, api_key, payload):
        payloads.append(payload)
        return _reply(_three_axes())

    profile = choose_profile_sync(
        _evidence_items(), mode="camera", settings=SETTINGS, cache=cache,
        client_call=_client,
    )
    assert len(payloads) == 1, "a complete answer must not be retried"
    assert profile.source == "vlm"
    assert [entry.name for entry in profile.axis_entries] == ["banding", "ringing"]
    assert profile.axis_ids == ("sharpness",)
    counts = axis_count_report(profile)
    assert counts == {
        "judged": 2,
        "judged_with_local_detector": 0,
        "registry": 1,
        "total": 3,
    }, "the count is stated honestly: 2 from the judge, 1 measured locally"


def test_an_axis_with_an_empty_why_is_retried_then_refused(tmp_path, caplog) -> None:
    cache = ProfileCache(tmp_path)
    payloads: list = []
    rows = _three_axes()
    rows[1]["why"] = "   "  # one axis left unexplained, twice

    def _client(base_url, api_key, payload):
        payloads.append(payload)
        return _reply(rows)

    with caplog.at_level(logging.WARNING, logger=APP_LOGGER_NAME):
        profile = choose_profile_sync(
            _evidence_items(), mode="camera", settings=SETTINGS, cache=cache,
            client_call=_client,
        )

    assert len(payloads) == 2, "one retry, then the fallback"
    assert profile.source != "vlm"
    warnings = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert any("`why` evidence" in text for text in warnings), (
        "an axis with no observed difference is refused with its reason"
    )
    assert "why" in payloads[1]["messages"][0]["content"][0]["text"], (
        "the retry asks for the missing tie explicitly"
    )


# ---------------------------------------------------------------------------
# (f) no evidence ⇒ no profile request
# ---------------------------------------------------------------------------


def test_an_empty_salience_summary_spends_no_request(tmp_path, caplog) -> None:
    cache = ProfileCache(tmp_path)
    calls: list = []

    def _client(*args, **kwargs):
        calls.append(1)
        return _reply(_three_axes())

    items = [  # no measured metric at all: nothing separates this series
        SimpleNamespace(path=Path("/gallery/a.png"), mtime_ns=1, metrics={}),
        SimpleNamespace(path=Path("/gallery/b.png"), mtime_ns=1, metrics={}),
    ]
    with caplog.at_level(logging.WARNING, logger=APP_LOGGER_NAME):
        profile = choose_profile_sync(
            items, mode="camera", settings=SETTINGS, cache=cache, client_call=_client
        )

    assert calls == [], "no measured difference ⇒ the call is not worth its cost"
    assert profile.source != "vlm"
    assert any(
        "no salience evidence" in r.getMessage()
        for r in caplog.records
        if r.levelno >= logging.WARNING
    ), "the skip is a WARN, not a silent no-op"
    assert cache.get(
        __import__(
            "tabs.image_gallery.services.profile_cache", fromlist=["profile_cache_key"]
        ).profile_cache_key(
            items, mode="camera", model="m",
            base_url="https://openrouter.ai/api/v1", reasoning_effort="auto",
        )
    ) is not None, "the offer the run used is still pinned"


# ---------------------------------------------------------------------------
# (d) per-SERIES resolution: the folder answer is the seed
# ---------------------------------------------------------------------------


def _series_item(name: str, **metrics) -> GalleryItem:
    item = GalleryItem(path=Path(f"/gallery/{name}"), mtime_ns=1)
    item.metrics.update(metrics)
    return item


def test_a_multi_group_folder_resolves_one_profile_per_series() -> None:
    seed = MetricProfile(
        axis_ids=("sharpness", "noise"),
        mode="camera",
        source="vlm",
        axis_entries=(JUDGED_A,),
    )
    moving = [  # sharpness separates these two, noise does not
        _series_item("m1.png", sharpness=0.0, noise=0.3),
        _series_item("m2.png", sharpness=400.0, noise=0.3),
    ]
    flat = [  # nothing separates these two
        _series_item("f1.png", sharpness=200.0, noise=0.3),
        _series_item("f2.png", sharpness=200.0, noise=0.3),
    ]
    groups = [SimpleNamespace(id="s1", members=moving), SimpleNamespace(id="s2", members=flat)]

    resolved = per_series_profiles(groups, mode="camera", seed=seed)

    assert len(resolved) == 2
    first, second = (profile for _group, profile in resolved)
    assert first.axis_ids == ("sharpness",), (
        "the first series is ranked on the axis that actually moves inside it"
    )
    assert second.axis_ids == ("sharpness", "noise"), (
        "a series with no local spread falls back to the folder answer (the seed)"
    )
    assert first.axis_entries == (JUDGED_A,) and second.axis_entries == (JUDGED_A,), (
        "the judge's free axes are the folder-level choice: every series carries them"
    )
    assert first.source == "vlm" and second.source == "vlm"


def test_a_multi_group_folder_logs_one_profile_line_per_series(monkeypatch, caplog) -> None:
    monkeypatch.setenv("IMGSLI_AI_DEBUG", "1")
    seed = MetricProfile(axis_ids=("sharpness",), mode="camera", source="series")
    groups = [
        SimpleNamespace(
            id="s1",
            members=[
                _series_item("a1.png", sharpness=0.0),
                _series_item("a2.png", sharpness=400.0),
            ],
        ),
        SimpleNamespace(
            id="s2",
            members=[
                _series_item("b1.png", sharpness=0.0),
                _series_item("b2.png", sharpness=100.0),
            ],
        ),
    ]
    owner = SimpleNamespace(
        state=SimpleNamespace(
            items=[m for g in groups for m in g.members],
            series=groups,
            mode="camera",
            metric_profile=seed,
            source_path=None,
        ),
        _judgment_domain="algorithms",
        widget=SimpleNamespace(
            set_rank_provenance=lambda *a, **k: None,
            set_ranks_visible=lambda *a, **k: None,
        ),
    )
    owner._refresh_rank_provenance = lambda: None
    owner._maybe_announce_done = lambda: None

    with caplog.at_level(logging.INFO, logger=APP_LOGGER_NAME):
        GalleryController._apply_fusion_ranks(owner, groups, mode="camera")

    lines = [r.getMessage() for r in caplog.records if "series profile:" in r.getMessage()]
    assert len(lines) == 2, f"one line per series (got {lines})"
    assert any("id=s1" in line for line in lines)
    assert any("id=s2" in line for line in lines)


def test_a_single_group_folder_uses_the_folder_profile() -> None:
    seed = MetricProfile(axis_ids=("sharpness",), mode="camera", source="series")
    assert measured_axes_for("camera", profile=seed) == ("sharpness",)
    # The mode mapping is still the fallback when there is no profile at all.
    assert measured_axes_for("camera", profile=None) == profile_for_mode("camera").axis_ids


# ---------------------------------------------------------------------------
# the honest count: log + UI state
# ---------------------------------------------------------------------------


def test_the_axis_count_is_stated_in_the_log_and_the_strip(monkeypatch, caplog, qtbot) -> None:
    from tabs.image_gallery.ui.stats_strip import StatsStrip

    monkeypatch.setenv("IMGSLI_AI_DEBUG", "1")
    profile = MetricProfile(
        axis_ids=("sharpness",), mode="camera", source="vlm", axis_entries=(JUDGED_A,)
    )
    strip = StatsStrip()
    qtbot.addWidget(strip)
    owner = SimpleNamespace(
        state=SimpleNamespace(metric_profile=profile),
        widget=SimpleNamespace(stats_strip=strip),
    )

    with caplog.at_level(logging.INFO, logger=APP_LOGGER_NAME):
        GalleryController._trace_axis_provenance(owner)

    text = "\n".join(r.getMessage() for r in caplog.records)
    assert "1 axes from the judge" in text, (
        "the count is a fact about the profile and must be stated, not implied"
    )
    assert "measured locally" in text
    assert strip.axis_counts == (1, 0, 1), "the UI holds the same three numbers"
    assert "measured by the judge" in strip.rank_provenance_label.toolTip()


def test_the_prompt_carries_no_axis_name_literal() -> None:
    from tabs.image_gallery.use_cases.profile_ai_request import _selector_text

    summary = profile_probe.salience_summary(_evidence_items(), probes=_evidence_items())
    text = _selector_text(summary)
    for retired in (
        "clarity",
        "hallucination",
        "banding",
        "white_balance",
        "jpeg_noise",
        "halation",
        "posterization",
    ):
        assert retired not in text, (
            f"the retired example axis {retired!r} is back in the selector prompt"
        )
