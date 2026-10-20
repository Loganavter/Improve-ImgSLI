"""W3 read path: per-axis provenance records (``analysis.read``).

``plan-gallery-analysis-engine-2026-10-20`` §Invariants I1/I6 and defect B6: a
surface must receive an ``AxisValue`` whose producer travels with the value, and
a missing axis must be a ``gap`` with a reason instead of vanishing from a
per-domain dict. These tests pin that contract, the "a gap is never filled from
the other domain" red-before story, the unchanged ``domain_axis_scores`` view,
and that dots/rows actually consume the reader (an AST assertion — reverting the
wiring to ``quality_read.domain_axis_scores`` fails it).
"""

from __future__ import annotations

import ast
from pathlib import Path

from engine.analysis.contracts import AxisValue
from tabs.image_gallery.analysis.read import (
    AI_PRODUCER,
    AXIS_UNMEASURED_REASON,
    AXIS_UNSCORED_REASON,
    ENGINE_GAP_REASON,
    ENGINE_PRODUCER,
    LOCAL_PRODUCER,
    NOT_ANALYZED_REASON,
    read_artifact_severities,
    read_axes,
    read_axis,
)
from tabs.image_gallery.models import AiAnalysisResult, AiDefect, GalleryItem
from tabs.image_gallery.services import quality_read
from tabs.image_gallery.services.rank_fusion import measured_axes_for
from tabs.image_gallery.ui.card.dots import metric_dots_for_item

GALLERY = Path(__file__).resolve().parents[1]


def _item(**kwargs) -> GalleryItem:
    item = GalleryItem(path=Path(kwargs.pop("name", "a.png")), mtime_ns=1)
    for key, value in kwargs.items():
        setattr(item, key, value)
    return item


def _analysis(**kwargs) -> AiAnalysisResult:
    return AiAnalysisResult(
        description="", tags=(), model="m", analyzed_at_iso="t", **kwargs
    )


# ---------------------------------------------------------------------------
# provenance
# ---------------------------------------------------------------------------


def test_ai_domain_reads_the_model_value_with_the_vlm_producer():
    item = _item(
        metrics={"sharpness": 320.0},  # the detector would say 80
        analysis=_analysis(axes={"sharpness": 33}),
    )
    record = read_axis(item, axis="sharpness", domain="ai")
    assert record.value == 33.0
    assert int(record.value) == 33
    assert record.producer == AI_PRODUCER == "vlm"
    assert record.status == "ok"
    assert record.backend is None  # the catalog supplies it in W5, not the reader


def test_algorithms_domain_reads_the_detector_value_with_the_local_producer():
    item = _item(
        metrics={"sharpness": 320.0},
        analysis=_analysis(axes={"sharpness": 33}),  # the VLM would say 33
    )
    record = read_axis(item, axis="sharpness", domain="algorithms")
    assert int(record.value) == 80  # 320 / 400 quality
    assert record.producer == LOCAL_PRODUCER == "local"
    assert record.status == "ok"


# ---------------------------------------------------------------------------
# gaps: status + reason, in both domains, and never a value
# ---------------------------------------------------------------------------


def test_missing_axis_is_a_gap_with_a_reason_in_both_domains():
    analyzed = _item(analysis=_analysis(axes={"sharpness": 33}))
    measured = _item(metrics={"sharpness": 200.0})

    ai_gap = read_axis(analyzed, axis="ssim", domain="ai")
    assert ai_gap.status == "gap"
    assert ai_gap.value is None
    assert ai_gap.reason == AXIS_UNSCORED_REASON
    assert ai_gap.producer == AI_PRODUCER

    local_gap = read_axis(measured, axis="ssim", domain="algorithms")
    assert local_gap.status == "gap"
    assert local_gap.value is None
    assert local_gap.reason == AXIS_UNMEASURED_REASON
    assert local_gap.producer == LOCAL_PRODUCER

    assert ai_gap.reason.strip() and local_gap.reason.strip()


def test_unanalyzed_item_gaps_with_the_not_analyzed_reason():
    """No exception, no empty tuple: every requested axis says why it is empty."""
    item = _item(metrics={"sharpness": 200.0})  # measured, never analyzed
    records = read_axes(item, domain="ai", axes=("sharpness", "noise"))
    assert [r.axis for r in records] == ["sharpness", "noise"]
    assert all(r.status == "gap" and r.value is None for r in records)
    assert all(r.reason == NOT_ANALYZED_REASON for r in records)


# ---------------------------------------------------------------------------
# the red-before story: a gap must NOT borrow the other domain's number
# ---------------------------------------------------------------------------


def test_ai_gap_is_not_filled_with_the_detector_number():
    """Detector measured ``ssim``; the AI domain still reports a gap.

    Before the read path, ``domain_axis_scores`` swapped whole dicts, so a
    partially-analyzed item silently lost nothing — and a full swap meant the
    other domain's number was one lookup away. The record must stay ``gap``.
    """
    item = _item(metrics={"ssim": 0.94})  # a detector value exists
    assert item.analysis is None
    record = read_axis(item, axis="ssim", domain="ai")
    assert record.status == "gap"
    assert record.value is None
    assert record.reason.strip()
    # And the detector number is still reachable only through its own domain.
    assert int(read_axis(item, axis="ssim", domain="algorithms").value) == 94


def test_algorithms_gap_is_not_filled_with_the_model_number():
    """Mirror case: the VLM scored ``ssim`` alone; the Algorithms read is a gap."""
    item = _item(analysis=_analysis(axes={"ssim": 88}))  # model value exists
    record = read_axis(item, axis="ssim", domain="algorithms")
    assert record.status == "gap"
    assert record.value is None
    assert record.reason.strip()
    assert int(read_axis(item, axis="ssim", domain="ai").value) == 88


# ---------------------------------------------------------------------------
# W9: engine records are preferred, and a gap stays a gap
# ---------------------------------------------------------------------------


def _record(
    axis: str,
    value: float | None,
    *,
    producer: str = "camera_scalars",
    status: str = "ok",
    reason: str = "",
) -> AxisValue:
    return AxisValue(
        axis=axis, value=value, producer=producer, status=status, reason=reason
    )


def test_engine_record_is_preferred_over_both_legacy_sources():
    """The record wins even when the domain's own primitive disagrees."""
    item = _item(
        metrics={"sharpness": 320.0},  # local detector would say 80
        analysis=_analysis(axes={"sharpness": 33}),  # VLM would say 33
        analysis_records=(_record("sharpness", 12.0),),
    )
    algorithms = read_axis(item, axis="sharpness", domain="algorithms")
    ai = read_axis(item, axis="sharpness", domain="ai")
    # Preference, not merge: the engine record answers both domains.
    for record in (algorithms, ai):
        assert record.status == "ok"
        assert record.value == 12.0
        assert record.producer == "camera_scalars"


def test_engine_gap_is_never_filled_from_the_legacy_value():
    """Red-before for W9: a record gap must not borrow ``item.metrics``/AI.

    Both legacy sources HAVE a value for ``sharpness`` here. Before the
    no-fallback rule the reader would answer from them, hiding the engine's
    "I have nothing" behind a number that a different producer measured.
    """
    item = _item(
        metrics={"sharpness": 320.0},
        analysis=_analysis(axes={"sharpness": 33}),
        analysis_records=(
            _record(
                "sharpness",
                None,
                status="gap",
                reason="the shared proxy decoded nothing",
            ),
        ),
    )
    for domain in ("algorithms", "ai"):
        record = read_axis(item, axis="sharpness", domain=domain)
        assert record.status == "gap"
        assert record.value is None
        assert record.reason == "the shared proxy decoded nothing"


def test_requested_axis_without_a_record_is_an_engine_gap():
    """No record for the axis = gap with the engine reason, never legacy."""
    item = _item(
        metrics={"sharpness": 320.0},
        analysis=_analysis(axes={"sharpness": 33}),
        analysis_records=(_record("noise", 71.0),),
    )
    record = read_axis(item, axis="sharpness", domain="algorithms")
    assert record.status == "gap"
    assert record.value is None
    assert record.reason == ENGINE_GAP_REASON
    assert record.producer == ENGINE_PRODUCER


def test_item_without_engine_records_keeps_the_legacy_read_exactly():
    """Flag-off shape: ``analysis_records == ()`` → today's dicts and records."""
    item = _item(
        metrics={"sharpness": 200.0, "noise": 0.9},
        analysis=_analysis(axes={"sharpness": 33}, composition=44),
    )
    assert item.analysis_records == ()
    assert quality_read.domain_axis_scores(item, domain="ai") == {
        "sharpness": 33,
        "composition": 44,
    }
    assert quality_read.domain_axis_scores(item, domain="algorithms") == {
        "sharpness": 50,
        "noise": 10,
    }
    ai = read_axes(item, domain="ai", axes=("sharpness", "noise"))
    assert [
        (r.axis, r.value, r.producer, r.status, r.reason) for r in ai
    ] == [
        ("sharpness", 33.0, AI_PRODUCER, "ok", ""),
        ("noise", None, AI_PRODUCER, "gap", AXIS_UNSCORED_REASON),
    ]


def test_engine_records_keep_requested_order_one_per_axis():
    """Requested axes come back verbatim, one record each, in order."""
    records = (_record("noise", 71.0), _record("sharpness", 12.0))
    item = _item(analysis_records=records)

    ordered = read_axes(item, domain="ai", axes=("sharpness", "ssim", "noise"))
    assert [r.axis for r in ordered] == ["sharpness", "ssim", "noise"]
    assert [r.status for r in ordered] == ["ok", "gap", "ok"]
    # The present records are the engine's own objects (provenance intact).
    assert ordered[0] is records[1]
    assert ordered[2] is records[0]
    assert ordered[1].reason == ENGINE_GAP_REASON

    # axes=None reports the records' order (plan order), not a legacy dict's.
    assert [r.axis for r in read_axes(item, domain="algorithms")] == [
        "noise",
        "sharpness",
    ]


def test_proxy_delivery_attaches_records_only_when_the_entry_carries_them():
    """The flag-ON key is copied; its absence leaves the item untouched."""
    from types import SimpleNamespace

    from tabs.image_gallery.use_cases.proxy_pass import _attach_analysis_records

    record = _record("sharpness", 12.0)
    item = _item(name="a.png")
    owner = SimpleNamespace(state=SimpleNamespace(items=[item]))

    # Flag-off batch entry: no "analysis" key → transient field stays empty.
    _attach_analysis_records(owner, {str(item.path): {"artifacts": {}}})
    assert item.analysis_records == ()

    # Flag-on entry: the records are attached as a tuple.
    _attach_analysis_records(owner, {str(item.path): {"analysis": (record,)}})
    assert item.analysis_records == (record,)


# ---------------------------------------------------------------------------
# axis selection + the unchanged dict view
# ---------------------------------------------------------------------------


def test_axes_none_reports_the_source_axes_and_a_list_is_returned_verbatim():
    item = _item(analysis=_analysis(axes={"noise": 91, "sharpness": 33}))
    reported = read_axes(item, domain="ai")
    assert [r.axis for r in reported] == ["noise", "sharpness"]  # dict order

    requested = read_axes(item, domain="ai", axes=("sharpness", "ssim", "noise"))
    assert [r.axis for r in requested] == ["sharpness", "ssim", "noise"]
    assert [r.status for r in requested] == ["ok", "gap", "ok"]


def test_domain_axis_scores_is_unchanged_for_a_fully_populated_item():
    item = _item(
        metrics={"sharpness": 200.0, "noise": 0.9},
        analysis=_analysis(axes={"sharpness": 33, "noise": 91}, composition=44),
    )
    assert quality_read.domain_axis_scores(item, domain="ai") == {
        "sharpness": 33,
        "noise": 91,
        "composition": 44,
    }
    assert quality_read.domain_axis_scores(item, domain="algorithms") == {
        "sharpness": 50,
        "noise": 10,
    }


def test_artifact_severities_are_delegated_not_reimplemented():
    item = _item(
        analysis=_analysis(defects=(AiDefect(kind="halo", severity="flagged"),))
    )
    assert read_artifact_severities(item, domain="ai") == {"halo": "flagged"}
    assert read_artifact_severities(item, domain="algorithms") == {}


# ---------------------------------------------------------------------------
# the consumers actually consume the reader
# ---------------------------------------------------------------------------


def _imported_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == (
            "tabs.image_gallery.analysis.read"
        ):
            names.update(alias.name for alias in node.names)
    return names


def _calls_attribute(path: Path, attr: str) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == attr
        for node in ast.walk(tree)
    )


def test_dots_and_rows_read_through_the_axis_reader():
    """Reverting the wiring to ``quality_read.domain_axis_scores`` fails here."""
    for relative in ("ui/card/dots.py", "ui/quick_look/metrics/rows.py"):
        path = GALLERY / relative
        assert "read_axes" in _imported_names(path), relative
        assert not _calls_attribute(path, "domain_axis_scores"), relative


def test_dots_show_the_domain_value_from_the_record():
    item = _item(
        metrics={"sharpness": 320.0},
        analysis=_analysis(axes={"sharpness": 33}),
    )
    index = measured_axes_for("camera").index("sharpness")
    _colors, ai_infos = metric_dots_for_item(item, mode="camera", domain="ai")
    _colors, local_infos = metric_dots_for_item(
        item, mode="camera", domain="algorithms"
    )
    assert ai_infos[index] == ("Sharpness", 33)
    assert local_infos[index] == ("Sharpness", 80)
    # Axes the AI domain did not score stay gaps (no number, muted dot).
    assert [score for i, (_label, score) in enumerate(ai_infos) if i != index] == [
        None
    ] * (len(ai_infos) - 1)
