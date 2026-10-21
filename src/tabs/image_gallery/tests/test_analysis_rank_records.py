"""W11 — rank fusion and salience read the engine's per-item records.

``plan-gallery-analysis-engine-2026-10-20`` W11: with the analysis engine on
(the DEFAULT since P9a; ``IMGSLI_ANALYSIS_ENGINE=0`` is the kill-switch) the
item carries scored ``AxisValue`` records (``item.analysis_records``); until
``item_quality`` and ``axis_spreads`` read them the legacy raw-metric path stays
load-bearing (the live run measured a 2.4x double computation). These tests pin
both readers and the rule that makes the legacy path droppable:

- **equivalence**: records derived from the same detector values produce the
  exact same qualities and rank order as the legacy raw path (weights and the
  worst-axis cap included);
- **a gap is not a zero** (red-before story): a ``gap`` record for an axis that
  *has* a raw value must exclude that axis, not score it 0 — a 0 would drag the
  mean down and the worst-axis cap would clamp the item to the slack;
- **a records-only item is measurable**: no ``item.metrics`` at all, still
  ranked (the engine is the source, not a decoration);
- **spreads**: the same values give the same spread from records, and a gap
  removes the item from that axis' spread (fewer than two values ⇒ omitted);
- **records win** over a disagreeing raw value (the engine's answer is
  authoritative) and only ``status="ok"`` counts (``stale`` is not a number).

Pure-python fakes + ``AxisValue`` only — no Qt, no torch, no PIL.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from engine.analysis.contracts import AxisValue
from tabs.image_gallery.services import rank_fusion
from tabs.image_gallery.services.metric_profile import axis_spreads
from tabs.image_gallery.services.metric_scores import score_for, spec_for
from tabs.image_gallery.services.rank_fusion import item_quality, rank_series


# ---------------------------------------------------------------------------
# fixtures: records derived from the SAME detector values as the legacy raws
# ---------------------------------------------------------------------------


def _record(axis: str, value: float | None, *, status: str = "ok") -> AxisValue:
    """One engine record; ``status="gap"`` must carry no value (contract)."""
    return AxisValue(axis=axis, value=value, producer="local", status=status)


def _records_from(metrics: dict) -> tuple[AxisValue, ...]:
    """The engine's answer for the detector values the legacy path scores."""
    return tuple(
        _record(axis, float(score_for(spec_for(axis), raw)))
        for axis, raw in metrics.items()
    )


def _item(name: str, records=(), **metrics) -> SimpleNamespace:
    return SimpleNamespace(
        path=Path(f"/gallery/{name}"),
        metrics=dict(metrics),
        analysis_records=tuple(records),
    )


#: Four items on two applicable axes (ssim is reference, noise untagged). The
#: worst-axis cap is load-bearing: c's plain mean is 60 but ssim 20 caps it to
#: 40, d's mean is 40 but noise 0 caps it to 20.
_DETECTORS: tuple[tuple[str, dict[str, float]], ...] = (
    ("a.png", {"ssim": 0.90, "noise": 0.10}),  # 90, 90 → 90
    ("b.png", {"ssim": 0.50, "noise": 0.50}),  # 50, 50 → 50
    ("c.png", {"ssim": 0.20, "noise": 0.00}),  # 20, 100 → mean 60, cap 40
    ("d.png", {"ssim": 0.80, "noise": 1.00}),  # 80, 0 → mean 40, cap 20
)


def _legacy_items() -> list[SimpleNamespace]:
    return [_item(name, **metrics) for name, metrics in _DETECTORS]


def _record_items() -> list[SimpleNamespace]:
    return [
        _item(name, _records_from(metrics), **metrics) for name, metrics in _DETECTORS
    ]


# ---------------------------------------------------------------------------
# equivalence: records reproduce the legacy numbers and order exactly
# ---------------------------------------------------------------------------


def test_records_reproduce_the_legacy_rank_and_qualities():
    legacy = _legacy_items()
    recorded = _record_items()

    legacy_quality = [item_quality(item, mode="fidelity") for item in legacy]
    # The legacy numbers are unchanged by this wave (the flag-off path).
    assert legacy_quality == [90.0, 50.0, 40.0, 20.0]
    assert [item_quality(item, mode="fidelity") for item in recorded] == legacy_quality

    legacy_ranks = rank_series(legacy, mode="fidelity")
    recorded_ranks = rank_series(recorded, mode="fidelity")
    assert recorded_ranks == legacy_ranks
    assert recorded_ranks == {
        "/gallery/a.png": 1,
        "/gallery/b.png": 2,
        "/gallery/c.png": 3,
        "/gallery/d.png": 4,
    }


def test_records_reproduce_the_legacy_numbers_under_axis_weights(monkeypatch):
    # The weight table and the worst-axis cap must behave identically in both
    # modes — records are just pre-scored values, not a second aggregation.
    monkeypatch.setitem(rank_fusion.RANK_AXIS_WEIGHTS, "fidelity", {"noise": 3.0})
    legacy = [item_quality(item, mode="fidelity") for item in _legacy_items()]
    recorded = [item_quality(item, mode="fidelity") for item in _record_items()]
    assert recorded == legacy


def test_zero_weight_removes_a_records_axis_too(monkeypatch):
    item = _item(
        "w.png", (_record("ssim", 100.0), _record("noise", 0.0)), ssim=1.0, noise=1.0
    )
    assert item_quality(item, mode="fidelity") == 20.0  # capped: min(50, 0+20)
    monkeypatch.setitem(rank_fusion.RANK_AXIS_WEIGHTS, "fidelity", {"noise": 0.0})
    assert item_quality(item, mode="fidelity") == 100.0  # noise dropped entirely


# ---------------------------------------------------------------------------
# a gap is excluded — never counted as 0, never backfilled from the raw dict
# ---------------------------------------------------------------------------


def test_a_gap_record_excludes_the_axis_instead_of_scoring_it_zero():
    # Legacy: (90 + 50) / 2 = 70. A gap counted as 0 would give min(45, 20) = 20;
    # an excluded axis gives 90. Both alternatives are visibly different.
    legacy = _item("g.png", ssim=0.90, noise=0.50)
    gapped = _item(
        "g.png",
        (_record("ssim", 90.0), _record("noise", None, status="gap")),
        ssim=0.90,
        noise=0.50,
    )
    assert item_quality(legacy, mode="fidelity") == 70.0
    assert item_quality(gapped, mode="fidelity") == 90.0


def test_only_ok_records_are_ranked():
    # ``stale`` carries a value but is not an independent measurement; an item
    # with no legacy metrics and only a stale record stays unmeasured.
    item = _item("s.png", (_record("ssim", 90.0, status="stale"),))
    assert item_quality(item, mode="fidelity") is None


# ---------------------------------------------------------------------------
# a records-only item is measurable (no raw dict at all)
# ---------------------------------------------------------------------------


def test_a_records_only_item_is_measurable_and_ranks():
    records_only = _item("records.png", (_record("sharpness", 100.0),))
    legacy_low = _item("legacy.png", sharpness=0.0)  # score 0
    unmeasured = _item("unmeasured.png")

    assert records_only.metrics == {}
    assert item_quality(records_only, mode="batch_synthetic") == 100.0
    ranks = rank_series([unmeasured, legacy_low, records_only], mode="batch_synthetic")
    assert ranks["/gallery/records.png"] == 1
    assert ranks["/gallery/legacy.png"] == 2
    assert ranks["/gallery/unmeasured.png"] == 3


# ---------------------------------------------------------------------------
# salience (axis_spreads) reads records too
# ---------------------------------------------------------------------------


def test_axis_spreads_match_legacy_for_the_same_values():
    legacy = axis_spreads(_legacy_items())
    recorded = axis_spreads(_record_items())
    assert recorded == legacy
    # sharpness is absent everywhere (no values), ssim spans 20..90, noise 0..100.
    assert recorded == {"ssim": 70.0, "noise": 100.0}


def test_a_gap_record_removes_the_item_from_the_axis_spread():
    legacy = [_item("a.png", sharpness=0.0), _item("b.png", sharpness=400.0)]
    assert axis_spreads(legacy) == {"sharpness": 100.0}

    gapped = [
        _item("a.png", (_record("sharpness", 0.0),), sharpness=0.0),
        # The raw value would score 100, but the engine says there is no number.
        _item("b.png", (_record("sharpness", None, status="gap"),), sharpness=400.0),
    ]
    assert "sharpness" not in axis_spreads(gapped)  # one value is not a spread


def test_axis_spreads_fall_back_to_raws_per_axis_without_a_record():
    # The rule is per axis, not per item: an axis with no record keeps the
    # legacy raw→score value, an axis with a gap record is excluded.
    recorded = _item(
        "a.png",
        (_record("sharpness", 100.0),),
        sharpness=400.0,
        noise=0.0,
    )
    legacy = _item("b.png", noise=1.0)
    spreads = axis_spreads([recorded, legacy])
    assert spreads["noise"] == 100.0  # no noise record → legacy raw→score
    assert "sharpness" not in spreads  # a single record value is no spread


# ---------------------------------------------------------------------------
# records are the engine's answer — they win over a disagreeing raw value
# ---------------------------------------------------------------------------


def test_records_win_over_metrics_when_they_disagree():
    a = _item("a.png", (_record("ssim", 10.0),), ssim=0.90)  # legacy 90
    b = _item("b.png", (_record("ssim", 90.0),), ssim=0.10)  # legacy 10

    assert item_quality(a, mode="fidelity") == 10.0
    assert item_quality(b, mode="fidelity") == 90.0
    # The legacy order (a first) is inverted by the records.
    assert rank_series([a, b], mode="fidelity")["/gallery/b.png"] == 1
