"""Adaptive sampling: the judge stops drawing when the median settles.

Board rule (``plan-gallery-ai-judgement`` follow-up, ``judge-adaptk``):
``AiSettings.sample_count`` is a CAP, not a quota. Draw 1 is always taken and
another draw is added only while a per-axis median still moves by more than HALF
the noise floor measured on this card's own draws
(``quality_read.axis_noise_floor``; its constant fallback is reachable only while
fewer than two draws exist, i.e. at the 2nd draw).

Why the published adaptive-sampling papers are not proof here: Adaptive-
Consistency (arXiv:2305.11860) / ESC stop on a DISCRETE answer distribution and
confirm it by majority vote; our axes are CONTINUOUS scores aggregated by a
median, so a settled median is evidence of stability, never of accuracy. The
tests below therefore validate the rule on a replay against a fixed-k median
instead of citing agreement rates.

The replay harness feeds synthetic per-draw scorecards through the real
``analyze_image_sync`` loop (transport/parse are stubbed), so the number of
counted calls is the loop's own behaviour, not a re-implementation.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from statistics import median
from types import SimpleNamespace

import pytest

import tabs.image_gallery.services.ai_client as ai_client
from tabs.image_gallery.models import AiAnalysisResult
from tabs.image_gallery.services import ai_cache
from tabs.image_gallery.services.ai_client.parse import median_drift
from tabs.image_gallery.services.ai_settings_store import AiSettings
from core.log_names import APP_LOGGER_NAME

AXES = ("sharpness", "noise", "exposure")
STAMP = "2026-01-01T00:00:00+00:00"


# ---------------------------------------------------------------------------
# harness: drive the real loop with a synthetic draw replay
# ---------------------------------------------------------------------------


def _result(axes: dict[str, int]) -> AiAnalysisResult:
    """One draw scorecard (the shape ``parse_response`` returns)."""
    return AiAnalysisResult(
        description="",
        tags=(),
        model="m",
        analyzed_at_iso=STAMP,
        axes=dict(axes),
        sharpness=int(axes.get("sharpness", -1)),
        noise=int(axes.get("noise", -1)),
        exposure=int(axes.get("exposure", -1)),
        composition=-1,
    )


def _run_card(
    monkeypatch,
    path: Path,
    draw_rows: list[dict[str, int]],
    *,
    samples: int,
    counter: dict,
    **kwargs,
) -> AiAnalysisResult:
    """Analyze ONE card through the real loop with *draw_rows* as its draws.

    Wire/transport/parse are stubbed; every parse call is one image call and is
    counted in ``counter["calls"]`` — the number the cost assertions use.
    """
    queue = [_result(row) for row in draw_rows]

    def _parse(*_args, **_kwargs):
        counter["calls"] += 1
        return queue.pop(0)

    monkeypatch.setattr(
        ai_client,
        "encode_wire_path",
        lambda _path: SimpleNamespace(
            mime="image/png", edge=64, source_bytes=1, wire_bytes=1
        ),
    )
    monkeypatch.setattr(ai_client, "build_request", lambda *_a, **_k: {})
    monkeypatch.setattr(ai_client, "call_sync", lambda *_a, **_k: {})
    monkeypatch.setattr(ai_client, "parse_response", _parse)
    return ai_client.analyze_image_sync(
        path,
        base_url="https://h/v1",
        api_key="k",
        model="m",
        samples=samples,
        **kwargs,
    )


def _settings(**overrides) -> AiSettings:
    base = dict(
        enabled=True,
        base_url="https://h/v1",
        api_key="sk-secret",
        model="m",
        reasoning_effort="auto",
        sample_count=3,
    )
    base.update(overrides)
    return AiSettings(**base)


# ---------------------------------------------------------------------------
# (a) a settled replay stops before the cap and stays inside the cost budget
# ---------------------------------------------------------------------------


def test_a_settled_replay_stops_before_the_cap_within_the_cost_budget(monkeypatch):
    """Settled cards spend 2 of 3 draws; a cap-1 card spends its one draw.

    The rule's floor is two draws per adaptive card (a movement cannot be
    measured from one), so the honest budget mix is: 4 settled cap-3 cards at
    2 calls = 8, 4 cap-1 cards at 1 call = 4 → 12 calls over 8 cards = 1.5/card,
    i.e. ``<= 1.6 x cards`` and well below the fixed-k 3/card of a cap-3 run.
    """
    settled = [
        {"sharpness": 80, "noise": 20, "exposure": 60},
        {"sharpness": 81, "noise": 20, "exposure": 60},
        {"sharpness": 80, "noise": 20, "exposure": 60},  # never reached
    ]
    single = {"sharpness": 50, "noise": 40, "exposure": 70}
    replay = [settled] * 4 + [[single]] * 4
    counter = {"calls": 0}

    merged = []
    for index, rows in enumerate(replay):
        cap = 3 if index < 4 else 1
        merged.append(
            _run_card(
                monkeypatch,
                Path(f"/gallery/card{index}.png"),
                rows,
                samples=cap,
                counter=counter,
            )
        )

    cards = 8
    assert counter["calls"] == 12
    assert counter["calls"] <= 1.6 * cards
    # Every adaptive card stopped BEFORE its cap …
    for result in merged[:4]:
        assert len(getattr(result, "axis_samples", ())) == 2
    # … and the cap-1 cards still spent exactly their declared draw.
    for result in merged[4:]:
        assert len(getattr(result, "axis_samples", ())) <= 1


# ---------------------------------------------------------------------------
# (b) the settled answer is as close to the 9-draw median as fixed k=3
# ---------------------------------------------------------------------------

#: Ground truth: nine draw offsets whose median is 0 (a settled card: the first
#: two draws agree, the later ones wiggle inside the instrument's noise).
NINE_DRAW_OFFSETS = (0, 0, 1, -1, 2, -2, 0, 0, 0)

BASES = (
    {"sharpness": 60, "noise": 30, "exposure": 55},
    {"sharpness": 72, "noise": 45, "exposure": 66},
    {"sharpness": 51, "noise": 18, "exposure": 83},
    {"sharpness": 90, "noise": 60, "exposure": 40},
    {"sharpness": 44, "noise": 77, "exposure": 71},
    {"sharpness": 65, "noise": 22, "exposure": 58},
)


def _card_rows(base: dict[str, int]) -> list[dict[str, int]]:
    return [
        {axis: int(base[axis] + offset) for axis in AXES}
        for offset in NINE_DRAW_OFFSETS
    ]


def _mae_against_nine_draw_median(merged) -> float:
    """Mean absolute error of *merged*' axes vs the 9-draw median per axis."""
    errors: list[float] = []
    for base, result in zip(BASES, merged):
        rows = _card_rows(base)
        for axis in AXES:
            truth = median(row[axis] for row in rows)
            errors.append(abs(int(result.axes[axis]) - truth))
    return sum(errors) / len(errors)


def test_the_settled_median_is_within_a_third_of_a_point_of_fixed_k(monkeypatch):
    """Per-axis MAE vs the 9-draw median must match fixed k=3 within 0.3 points.

    This is the falsifiable form of "early stopping does not change the answer":
    the replay's first two draws agree, so the adaptive run settles at 2 draws
    while the fixed run spends all 3.
    """
    replay = [_card_rows(base) for base in BASES]
    counter = {"calls": 0}
    adaptive = [
        _run_card(
            monkeypatch,
            Path(f"/gallery/a{index}.png"),
            rows,
            samples=3,
            counter=counter,
        )
        for index, rows in enumerate(replay)
    ]
    assert counter["calls"] == 2 * len(BASES), counter

    monkeypatch.setenv("IMGSLI_ADAPTIVE_K_STOP", "0")
    counter = {"calls": 0}
    fixed = [
        _run_card(
            monkeypatch,
            Path(f"/gallery/f{index}.png"),
            rows,
            samples=3,
            counter=counter,
        )
        for index, rows in enumerate(replay)
    ]
    assert counter["calls"] == 3 * len(BASES), counter
    for result in fixed:
        assert len(result.axis_samples) == 3

    mae_adaptive = _mae_against_nine_draw_median(adaptive)
    mae_fixed = _mae_against_nine_draw_median(fixed)
    assert abs(mae_adaptive - mae_fixed) <= 0.3, (mae_adaptive, mae_fixed)


# ---------------------------------------------------------------------------
# (c) the cache identity carries the EFFECTIVE k (the red-before pair)
# ---------------------------------------------------------------------------


def _cache_dir(tmp_path, monkeypatch) -> Path:
    monkeypatch.setattr(ai_cache, "ai_cache_dir", lambda: tmp_path)
    return tmp_path


def test_a_one_draw_scorecard_is_never_served_for_a_cap_three_request(
    tmp_path, monkeypatch
):
    """Stored depth 1 vs request budget 3 is a MISS (red-before: it was a HIT)."""
    cache = _cache_dir(tmp_path, monkeypatch)
    path, mtime = Path("/gallery/frame.png"), 42
    request = ai_cache.analysis_cache_identity(_settings(sample_count=3), mode="camera")

    thin = AiAnalysisResult(
        description="one draw",
        tags=(),
        model="m",
        analyzed_at_iso=STAMP,
        axes={"sharpness": 80},
        axis_samples=({"sharpness": 80},),
    )
    ai_cache.save_analysis(path, mtime, thin, request)

    stored = json.loads(next(cache.glob("*.json")).read_text(encoding="utf-8"))
    assert stored["identity"]["k"] == "3", "k is the declared cap"
    assert stored["identity"]["effective_k"] == "1", "the payload records the depth"

    assert ai_cache.load_cached_analysis(path, mtime, request) is None


def test_an_unbudgeted_identity_declares_the_minimum_depth_not_a_fabricated_cap():
    """With no settings read, the identity must not claim a k it never saw."""
    identity = ai_cache.analysis_cache_identity(None, mode="camera")
    assert identity["k"] == "1"
    assert identity["effective_k"] == "1"
    # A real, budgeted request still declares its cap.
    budgeted = ai_cache.analysis_cache_identity(_settings(sample_count=3), mode="camera")
    assert budgeted["k"] == "3" and budgeted["effective_k"] == "3"


def test_a_full_depth_scorecard_still_hits_its_own_request(tmp_path, monkeypatch):
    """The same identity at the declared depth is a HIT — the cache is not off."""
    _cache_dir(tmp_path, monkeypatch)
    path, mtime = Path("/gallery/frame.png"), 42
    request = ai_cache.analysis_cache_identity(_settings(sample_count=3), mode="camera")
    thick = AiAnalysisResult(
        description="three draws",
        tags=(),
        model="m",
        analyzed_at_iso=STAMP,
        axes={"sharpness": 80},
        axis_samples=({"sharpness": 80}, {"sharpness": 81}, {"sharpness": 79}),
    )
    ai_cache.save_analysis(path, mtime, thick, request)

    hit = ai_cache.load_cached_analysis(path, mtime, request)
    assert hit is not None
    assert hit.axes["sharpness"] == 80


def test_the_cache_format_version_moved_past_the_pre_effective_k_shape(
    tmp_path, monkeypatch
):
    """A v3 payload (no ``effective_k``) can never be read as the new shape."""
    cache = _cache_dir(tmp_path, monkeypatch)
    assert ai_cache.AI_CACHE_VERSION >= 4
    path, mtime = Path("/gallery/frame.png"), 42
    request = ai_cache.analysis_cache_identity(_settings(sample_count=3), mode="camera")
    ai_cache.save_analysis(path, mtime, _result({"sharpness": 80}), request)

    entry = next(cache.glob("*.json"))
    data = json.loads(entry.read_text(encoding="utf-8"))
    data["version"] = ai_cache.AI_CACHE_VERSION - 1
    data["identity"].pop("effective_k", None)
    entry.write_text(json.dumps(data), encoding="utf-8")

    assert ai_cache.load_cached_analysis(path, mtime, request) is None


# ---------------------------------------------------------------------------
# (d) the one env knob restores the old fixed-k behaviour
# ---------------------------------------------------------------------------


def test_the_env_knob_restores_fixed_k(monkeypatch):
    """``IMGSLI_ADAPTIVE_K_STOP=0`` spends every declared draw again."""
    monkeypatch.setenv("IMGSLI_ADAPTIVE_K_STOP", "0")
    settled = [
        {"sharpness": 80, "noise": 20, "exposure": 60},
        {"sharpness": 81, "noise": 20, "exposure": 60},
        {"sharpness": 80, "noise": 20, "exposure": 60},
    ]
    counter = {"calls": 0}
    result = _run_card(
        monkeypatch, Path("/gallery/card.png"), settled, samples=3, counter=counter
    )

    assert counter["calls"] == 3
    assert len(result.axis_samples) == 3


def test_adaptive_is_the_default_and_can_be_forced_off_per_call(monkeypatch):
    """Unset = adaptive; the keyword-only argument overrides the env knob."""
    monkeypatch.delenv("IMGSLI_ADAPTIVE_K_STOP", raising=False)
    settled = [
        {"sharpness": 80, "noise": 20, "exposure": 60},
        {"sharpness": 81, "noise": 20, "exposure": 60},
        {"sharpness": 80, "noise": 20, "exposure": 60},
    ]
    counter = {"calls": 0}
    _run_card(
        monkeypatch, Path("/gallery/a.png"), settled, samples=3, counter=counter
    )
    assert counter["calls"] == 2

    counter = {"calls": 0}
    _run_card(
        monkeypatch,
        Path("/gallery/b.png"),
        settled,
        samples=3,
        counter=counter,
        adaptive_k=False,
    )
    assert counter["calls"] == 3


# ---------------------------------------------------------------------------
# (e) the trace names the effective k and the stopping reason
# ---------------------------------------------------------------------------


def _trace_lines(caplog) -> list[str]:
    return [
        record.getMessage()
        for record in caplog.records
        if "adaptive stop:" in record.getMessage()
    ]


@pytest.fixture
def ai_trace(monkeypatch, caplog):
    monkeypatch.setenv("IMGSLI_AI_DEBUG", "1")
    caplog.set_level(logging.INFO, logger=APP_LOGGER_NAME)
    return caplog


def test_the_trace_names_a_settled_stop(ai_trace, monkeypatch):
    settled = [
        {"sharpness": 80, "noise": 20, "exposure": 60},
        {"sharpness": 81, "noise": 20, "exposure": 60},
        {"sharpness": 80, "noise": 20, "exposure": 60},
    ]
    _run_card(
        monkeypatch, Path("/gallery/settled.png"), settled, samples=3, counter={"calls": 0}
    )

    lines = _trace_lines(ai_trace)
    assert len(lines) == 1, lines
    line = lines[0]
    assert line.startswith("[ai] adaptive stop:"), line
    assert "effective_k=2" in line and "cap=3" in line
    assert "reason=settled" in line


def test_the_trace_names_a_capped_stop_and_the_axis_still_moving(ai_trace, monkeypatch):
    """At the cap the budget wins: reason ``capped`` names the moving axis."""
    wild = [
        {"sharpness": 40, "noise": 20, "exposure": 60},
        {"sharpness": 90, "noise": 20, "exposure": 60},
    ]
    _run_card(
        monkeypatch, Path("/gallery/wild.png"), wild, samples=2, counter={"calls": 0}
    )

    lines = _trace_lines(ai_trace)
    assert len(lines) == 1, lines
    line = lines[0]
    assert "effective_k=2" in line and "cap=2" in line
    assert "reason=capped" in line
    assert "axis sharpness still moving" in line


# ---------------------------------------------------------------------------
# the pure helper, unit-tested directly
# ---------------------------------------------------------------------------


def test_median_drift_reports_the_movement_the_newest_draw_caused():
    assert median_drift([{"sharpness": 80}, {"sharpness": 84}]) == {
        "sharpness": 2.0
    }
    # The median of an odd set is the middle value: a wild 3rd draw on ONE axis
    # cannot move it (robust aggregation, by design).
    assert median_drift(
        [{"sharpness": 80}, {"sharpness": 80}, {"sharpness": 20}]
    ) == {"sharpness": 0.0}


def test_median_drift_filters_axes_and_ignores_unmeasurable_input():
    rows = [{"sharpness": 70, "noise": 10}, {"sharpness": 74, "noise": 14}]
    assert median_drift(rows, axes=["SHARPNESS"]) == {"sharpness": 2.0}
    assert median_drift([]) == {}
    assert median_drift([{"sharpness": 70}]) == {}
    # No axis scored twice: nothing comparable moved.
    assert median_drift([{"sharpness": 70}, {"noise": 10}]) == {}
    # A non-numeric score is skipped, never raised.
    assert median_drift([{"sharpness": "bad"}, {"sharpness": 72}]) == {}
