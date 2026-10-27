"""Quick Look metric rows follow the ACTIVE metric profile.

Live bug (2026-10-20): Quick Look rendered its own fixed per-mode row set
(7 labels) while the card dots showed the active profile's 2 axes and the
trace said ``axes=sharpness,noise source=vlm`` — three surfaces, three
truths. The rows are now derived from the same seam the dots read
(``profile_select.active_profile`` → ``rank_fusion.measured_axes_for``):
the profile decides which axes render, an in-profile axis with no score
stays an honest "not measured" row, an out-of-profile axis is absent, the
AI-only ``composition`` row belongs to the AI judgment domain only, and the
row cache fingerprint includes the profile (so a profile/domain change
rebuilds instead of replaying the old labels).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from PySide6.QtWidgets import QApplication, QWidget

from tabs.image_gallery.models import (
    AiAnalysisResult,
    AiAxisProposal,
    GalleryItem,
    Mode,
)
from tabs.image_gallery.services.metric_profile import MetricProfile
from tabs.image_gallery.ui.quick_look import QuickLookOverlay
from sli_ui_toolkit.ui.widgets.atomic.text_labels import Label as _QlLabel  # internal: documented Label exception (queue task-text-unification-retirement-2026-10-21)
from sli_ui_toolkit.widgets import Text as _QlText


def _qlabels(widget):
    """Row labels of *widget* from both widget families.

    Metric rows are built by ``_make_label``, which wave C migrated from the
    retired ``Label`` to painted ``Text``; scanning both keeps these row
    assertions addressing the same labels regardless of family.
    """
    return widget.findChildren(_QlLabel) + widget.findChildren(_QlText)


def _item(name: str, **kwargs) -> GalleryItem:
    return GalleryItem(path=Path(f"/gallery/{name}"), mtime_ns=1, **kwargs)


def _row_texts(overlay) -> list[str]:
    return [
        lbl.text()
        for row in overlay._metric_rows
        for lbl in _qlabels(row)
    ]


def _row_titles(overlay) -> list[str]:
    """Left-hand title labels only (the values are right-aligned)."""
    from PySide6.QtCore import Qt

    out: list[str] = []
    for row in overlay._metric_rows:
        for lbl in _qlabels(row):
            try:
                if bool(lbl.alignment() & Qt.AlignmentFlag.AlignRight):
                    continue
            except Exception:
                pass
            if lbl.text():
                out.append(lbl.text())
    return out


def _row_pairs(overlay) -> list[tuple[str, str]]:
    """``(title, value)`` per row — the unit the row-state tests address."""
    from PySide6.QtCore import Qt

    out: list[tuple[str, str]] = []
    for row in overlay._metric_rows:
        title = value = ""
        for lbl in _qlabels(row):
            right = False
            try:
                right = bool(lbl.alignment() & Qt.AlignmentFlag.AlignRight)
            except Exception:
                pass
            if right:
                value = value or lbl.text()
            else:
                title = title or lbl.text()
        out.append((title, value))
    return out


def _show(qtbot, item, series, *, mode=Mode.FIDELITY, domain=None, profile=None):
    # One slot per backend: a judge-tagged profile is the AI backend's, anything
    # else the Algorithms derivation's. ``domain=None`` infers from the tag.
    ai_tagged = str(getattr(profile, "source", "")) == "vlm"
    if domain is None:
        domain = "ai" if ai_tagged else "algorithms"
    algorithms_profile = None if ai_tagged else profile
    ai_profile = profile if ai_tagged else None
    parent = QWidget()
    qtbot.addWidget(parent)
    ov = QuickLookOverlay(parent)
    ov._parity_test_parent = parent  # strong ref keeps the C++ tree alive
    owner = SimpleNamespace(
        _judgment_domain=domain,
        state=SimpleNamespace(
            mode=mode,
            source_path=None,
            series=[list(series)],
            items=list(series),
            judgment_domain=domain,
            algorithms_profile=algorithms_profile,
            ai_profile=ai_profile,
        ),
    )
    ov.show_for(item, owner)
    parent.resize(1280, 800)
    parent.show()
    QApplication.processEvents()
    return ov


def test_quick_look_rows_follow_the_active_metric_profile(qtbot):
    """A 2-axis vlm profile renders exactly those two rows (not the mode set)."""
    profile = MetricProfile(
        axis_ids=("sharpness", "noise"), mode="fidelity", source="vlm"
    )
    item = _item(
        "vlm2.png",
        rank=1,
        metrics={"sharpness": 150.0, "noise": 0.2},
    )
    ov = _show(qtbot, item, [item], mode=Mode.FIDELITY, profile=profile)
    try:
        assert len(ov._metric_rows) == 2, _row_titles(ov)
        titles = _row_titles(ov)
        assert any(t.startswith("Sharpness") for t in titles), titles
        assert any(t.startswith("Clean") for t in titles), titles
        # Axes outside the active profile are not rendered at all.
        assert not any(t.startswith("Source match") for t in titles), titles
        assert not any(t.startswith("Detail") for t in titles), titles
    finally:
        ov.hide()

    # An in-profile axis with no measurement stays an honest gap row: the
    # profile still renders exactly its two axes, never a fabricated value.
    sparse = _item("vlm2-gap.png", rank=1, metrics={"sharpness": 150.0})
    ov_gap = _show(qtbot, sparse, [sparse], mode=Mode.FIDELITY, profile=profile)
    try:
        assert len(ov_gap._metric_rows) == 2, _row_titles(ov_gap)
        gap_texts = _row_texts(ov_gap)
        assert any(t.startswith("Clean") for t in gap_texts), gap_texts
        assert any("not measured" in t for t in gap_texts), gap_texts
    finally:
        ov_gap.hide()


def test_algorithms_domain_hides_the_ai_composition_row(qtbot):
    """Composition is a VLM axis, not a measured-pool axis: AI domain only."""
    item = _item(
        "comp.png",
        rank=1,
        metrics={"sharpness": 150.0, "noise": 0.2},
        analysis=AiAnalysisResult(
            description="",
            tags=(),
            model="m",
            analyzed_at_iso="t",
            axes={"sharpness": 80, "noise": 90, "composition": 77},
            composition=77,
        ),
    )
    profile = MetricProfile(
        axis_ids=("sharpness", "noise"), mode="fidelity", source="vlm"
    )
    ov = _show(
        qtbot, item, [item], mode=Mode.FIDELITY, domain="algorithms", profile=profile
    )
    try:
        titles = _row_titles(ov)
        assert any(t.startswith("Sharpness") for t in titles), titles
        assert not any(t.startswith("Composition") for t in titles), titles
        assert not any("77%" in t for t in _row_texts(ov)), _row_texts(ov)
    finally:
        ov.hide()

    ov_ai = _show(
        qtbot, item, [item], mode=Mode.FIDELITY, domain="ai", profile=profile
    )
    try:
        ai_titles = _row_titles(ov_ai)
        assert any(t.startswith("Composition") for t in ai_titles), ai_titles
    finally:
        ov_ai.hide()


def test_a_series_offer_renders_its_unscored_axis_as_not_measured(qtbot):
    """An OFFERED axis the judge never scored says so instead of vanishing.

    P5: ``source=series`` is an offer, not the wide mode pool — the rows must
    render exactly its axes, so an axis with no reading is a visible gap
    (M5 "every loss is a visible state"), not a silent omission.
    """
    from tabs.image_gallery.ui.quick_look import metrics as m

    item = _item("series-offer.png", rank=1, metrics={"sharpness": 150.0})
    offer = MetricProfile(
        axis_ids=("sharpness", "noise"), mode="fidelity", source="series"
    )
    ov = _RowsStub(item, offer)
    qtbot.addWidget(ov._report_host)
    m.rebuild_metrics(ov, item, True, "FIDELITY")

    titles = _row_titles(ov)
    assert any(t.startswith("Sharpness") for t in titles), titles
    assert any(t.startswith("Clean") for t in titles), (
        "the offered axis with no score was dropped instead of rendered as a "
        f"gap: {titles}"
    )
    assert any("not measured" in t for t in _row_texts(ov)), _row_texts(ov)


def test_a_mode_fallback_offer_adds_no_axis_set_row(qtbot):
    """The "Axis set — mode default" state row was REMOVED (owner, 2026-10-22).

    It named the fallback offer but carried no number and no action; the owner
    called it useless. The fallback's axes still render exactly as before — only
    the extra state row is gone, so the report starts with real measurements.
    """
    from tabs.image_gallery.ui.quick_look import metrics as m

    item = _item("fallback.png", rank=1, metrics={"sharpness": 150.0, "noise": 0.2})
    fallback = MetricProfile(
        axis_ids=("sharpness", "noise"), mode="fidelity", source="heuristic"
    )
    ov = _RowsStub(item, fallback)
    qtbot.addWidget(ov._report_host)
    m.rebuild_metrics(ov, item, True, "FIDELITY")

    texts = _row_texts(ov)
    assert "Axis set" not in texts, f"the removed state row came back: {texts}"
    assert "mode default" not in texts
    assert texts, "the report must still render its measured rows"

    # An accepted offer (series or the judge's own) is NOT a fallback.
    offered = MetricProfile(
        axis_ids=("sharpness", "noise"), mode="fidelity", source="series"
    )
    ov._owner.state.algorithms_profile = offered
    m.rebuild_metrics(ov, item, True, "FIDELITY")
    assert "mode default" not in _row_texts(ov), _row_texts(ov)


class _RowsStub:
    """Bare overlay surface for the row pipeline (no window, no layout)."""

    def __init__(self, item: GalleryItem, profile):
        self._metric_rows: list = []
        self._report_host = QWidget()
        self._metrics_host = self._report_host
        self._right_lay = None
        self._series_items = [item]
        self._current_idx = 0
        self._mode = Mode.FIDELITY
        self._source_path = None
        ai_tagged = str(getattr(profile, "source", "")) == "vlm"
        self._owner = SimpleNamespace(
            _judgment_domain=("ai" if ai_tagged else "algorithms"),
            state=SimpleNamespace(
                mode=Mode.FIDELITY,
                algorithms_profile=None if ai_tagged else profile,
                ai_profile=profile if ai_tagged else None,
            ),
        )


def test_ql_metrics_cache_invalidates_on_profile_change(qtbot):
    """Same item/metrics/mode, new active profile → rows rebuild (no stale replay)."""
    from tabs.image_gallery.ui.quick_look import metrics as m

    item = _item(
        "cacheprofile.png",
        rank=1,
        metrics={
            "sharpness": 150.0,
            "exposure": 0.5,
            "clipping": 0.4,
            "noise": 0.2,
        },
    )
    narrow = MetricProfile(
        axis_ids=("sharpness", "noise"), mode="fidelity", source="vlm"
    )
    ov = _RowsStub(item, narrow)
    qtbot.addWidget(ov._report_host)
    m.rebuild_metrics(ov, item, True, "FIDELITY")
    assert len(ov._metric_rows) == 2, _row_titles(ov)
    assert not any(t.startswith("Exposure") for t in _row_titles(ov))

    # Same series/item/metrics — only the active profile changes.
    ov._owner.state.ai_profile = MetricProfile(
        axis_ids=("sharpness", "exposure", "clipping", "noise"),
        mode="fidelity",
        source="vlm",
    )
    m.rebuild_metrics(ov, item, True, "FIDELITY")
    titles = _row_titles(ov)
    assert len(ov._metric_rows) == 4, titles
    assert any(t.startswith("Exposure") for t in titles), titles
    assert any(t.startswith("Highlight detail") for t in titles), titles


# ---------------------------------------------------------------------------
# Three DISTINCT row states (owner 2026-10-27, free-axes lane)
#
# scored        — the read record for THIS item carries a number;
# not measured  — no number exists for this item (no scorecard / axis added
#                 after the pass / an answer that carried no value / the -1
#                 sentinel) — NEVER the "constant" text;
# constant      — numbers DO exist and agree across the compared variants,
#                 which is a measurement fact, not a stand-in for a gap.
# ---------------------------------------------------------------------------

#: A judge-named axis (no local detector, no registry id).
_JUDGED = AiAxisProposal(
    name="line_crispness",
    definition="separated hairlines and micro-contrast; 0 = mush, 100 = crisp",
    direction="higher-is-better",
)


def _judged_item(name: str, **axes) -> GalleryItem:
    item = _item(name)
    item.analysis = AiAnalysisResult(
        description="", tags=(), model="m", analyzed_at_iso="t", axes=dict(axes)
    )
    return item


def _judged_profile(*entries: AiAxisProposal, axis_ids=("sharpness",)) -> MetricProfile:
    return MetricProfile(
        axis_ids=axis_ids,
        mode="camera",
        source="vlm",
        axis_entries=tuple(entries),
    )


def _build(qtbot, item, profile, series, *, domain="ai") -> "_RowsStub":
    from tabs.image_gallery.ui.quick_look import metrics as m

    ov = _RowsStub(item, profile)
    ov._series_items = list(series)
    qtbot.addWidget(ov._report_host)
    m.rebuild_metrics(ov, item, False, "CAMERA")
    return ov


def _value_for(overlay, needle: str) -> str:
    matches = [value for title, value in _row_pairs(overlay) if needle in title]
    assert len(matches) == 1, (needle, _row_pairs(overlay))
    return matches[0]


def test_the_three_row_states_are_distinct_and_a_missing_number_is_not_constant(qtbot):
    """Red before: the absent axis read "does not separate these variants".

    Fixture (what the owner's screenshot showed): the judge scored
    'line_crispness' 70 on two variants — equal, so inside the noise floor —
    and never scored it on the third (the open one). The third row said the
    axis "does not separate these variants", i.e. a missing number was
    rendered with the measured-constant text.
    """
    from tabs.image_gallery.services.rank_fusion import INSIDE_NOISE
    from tabs.image_gallery.ui.quick_look.metrics.rows import (
        ROW_STATE_CONSTANT,
        ROW_STATE_NOT_MEASURED,
        ROW_STATE_SCORED,
        axis_row_state,
    )

    profile = _judged_profile(_JUDGED)
    a = _judged_item("state_a.png", sharpness=80, **{_JUDGED.name: 70})
    b = _judged_item("state_b.png", sharpness=40, **{_JUDGED.name: 70})
    absent = _judged_item("state_c.png", sharpness=60)  # never scored here

    # (c) measured, equal across the compared variants -> constant state.
    ov_const = _build(qtbot, a, profile, [a, b, absent])
    try:
        assert _value_for(ov_const, _JUDGED.name) == "does not separate these variants"
        # (a) scored -> a number + bar.
        assert _value_for(ov_const, "Sharpness").endswith("%"), _row_pairs(ov_const)
    finally:
        ov_const._report_host.deleteLater()

    # (b) no number for this variant -> not measured, never the constant text.
    ov_gap = _build(qtbot, absent, profile, [a, b, absent])
    try:
        gap_value = _value_for(ov_gap, _JUDGED.name)
        assert gap_value == "— · not measured", (
            "an absent score was rendered as the measured-constant state: "
            f"{_row_pairs(ov_gap)}"
        )
        assert "does not separate" not in gap_value
    finally:
        ov_gap._report_host.deleteLater()

    # The ONE decision site encodes the precedence (gap outranks the verdict).
    verdict = {_JUDGED.name: INSIDE_NOISE}
    assert (
        axis_row_state(
            "sharpness",
            read={"sharpness": 60},
            salience=verdict,
            inside_noise=INSIDE_NOISE,
        )
        == ROW_STATE_SCORED
    )
    assert (
        axis_row_state(
            _JUDGED.name,
            read={"sharpness": 60},
            salience=verdict,
            inside_noise=INSIDE_NOISE,
        )
        == ROW_STATE_NOT_MEASURED
    )
    assert (
        axis_row_state(
            _JUDGED.name,
            read={_JUDGED.name: 70},
            salience=verdict,
            inside_noise=INSIDE_NOISE,
        )
        == ROW_STATE_CONSTANT
    )


def test_none_and_the_minus_one_sentinel_never_read_as_a_measurement(qtbot):
    """An absent value, a gap record and the -1 sentinel are all "not measured"."""
    from engine.analysis.contracts import AxisValue

    profile = _judged_profile(_JUDGED)
    reference = _judged_item("sentinel_ref.png", sharpness=80, **{_JUDGED.name: 70})
    twin = _judged_item("sentinel_twin.png", sharpness=40, **{_JUDGED.name: 70})
    # A judge axis the scorecard answered with its "unscored" sentinel.
    sentinel = _judged_item("sentinel_minus_one.png", sharpness=60, **{_JUDGED.name: -1})

    ov = _build(qtbot, sentinel, profile, [reference, twin, sentinel])
    try:
        assert _value_for(ov, _JUDGED.name) == "— · not measured", _row_pairs(ov)
    finally:
        ov._report_host.deleteLater()

    # An engine record can carry the same sentinel (or a gap) with status "ok":
    # the row reader must drop it, not paint "-1%" / "0%".
    for record in (
        AxisValue(axis=_JUDGED.name, value=-1.0, producer="vlm", status="ok"),
        AxisValue(axis=_JUDGED.name, value=None, producer="vlm", status="gap"),
        AxisValue(axis=_JUDGED.name, value=None, producer="vlm", status="error"),
    ):
        item = _judged_item("sentinel_record.png", sharpness=60)
        item.analysis_records = (record,)
        ov_rec = _build(qtbot, item, profile, [reference, twin, item])
        try:
            assert _value_for(ov_rec, _JUDGED.name) == "— · not measured", (
                record,
                _row_pairs(ov_rec),
            )
            assert not any(v.strip() in ("-1%", "0%") for _t, v in _row_pairs(ov_rec))
        finally:
            ov_rec._report_host.deleteLater()

    # A real 0 IS a measurement (the sentinel rule must not eat it).
    zero = _judged_item("sentinel_zero.png", sharpness=60, **{_JUDGED.name: 0})
    ov_zero = _build(qtbot, zero, profile, [zero])
    try:
        assert _value_for(ov_zero, _JUDGED.name) == "0%", _row_pairs(ov_zero)
    finally:
        ov_zero._report_host.deleteLater()


def test_a_judge_axis_without_a_definition_shows_its_name_alone(qtbot):
    """Owner rule 2026-10-27: a metric the model NAMED is drawn, definition or not."""
    from tabs.image_gallery.ui.quick_look.metrics.judged import judged_axis_title

    bare = AiAxisProposal(name="line_crispness", definition="")
    profile = _judged_profile(bare)
    # Owner rule 2026-10-27, and now the CODE agrees (wave W1): an entry with no
    # definition is KEPT by the normalizer, so the fixture no longer has to be
    # injected past it. The guard stays, inverted: the entry must SURVIVE, or the
    # row below is testing nothing.
    assert [e.name for e in profile.axis_entries] == [bare.name], (
        "fixture: the empty-definition entry must survive the entry normalizer",
    )

    # The wording rule itself: name alone, no dangling em-dash, no crash.
    assert judged_axis_title(bare.name, profile=profile) == (
        f"{bare.name} · measured by the judge"
    )

    item = _judged_item("no_definition.png", sharpness=80)  # the judge scored no axis
    ov = _build(qtbot, item, profile, [item])
    try:
        pairs = _row_pairs(ov)
        judged = [(t, v) for t, v in pairs if bare.name in t]
        assert judged, f"the judge's axis vanished without a definition: {pairs}"
        title = judged[0][0]
        assert title.startswith(bare.name), title
        assert f"{bare.name} — " not in title, (
            "an empty definition left a dangling em-dash instead of the name "
            f"alone: {title!r}"
        )
        assert judged[0][1] == "— · not measured", pairs
    finally:
        ov._report_host.deleteLater()


def test_a_judged_title_is_widened_so_the_axis_name_stays_whole(qtbot):
    """The elision falls on the definition, never on which axis this is.

    Red before: every judged title kept a fixed 140px floor, so the model's
    definition was cut to "— S…" on the owner's screen (2026-10-27).
    """
    from PySide6.QtGui import QFontMetricsF

    profile = _judged_profile(_JUDGED)
    item = _judged_item("title_width.png", sharpness=80, **{_JUDGED.name: 86})

    ov = _build(qtbot, item, profile, [item])
    try:
        rows = [
            (row, lbl)
            for row in ov._metric_rows
            for lbl in _qlabels(row)
            if _JUDGED.name in lbl.text() and lbl.text().strip() != "86%"
        ]
        assert rows, _row_pairs(ov)
        row, title = rows[0]
        full = title.get_original_text() if hasattr(title, "get_original_text") else title.text()
        assert full.endswith("· measured by the judge"), full
        need = int(QFontMetricsF(title.font()).horizontalAdvance(_JUDGED.name))
        assert title.minimumWidth() >= need, (
            "the title floor cannot hold the axis name — the elision would hide "
            f"which axis this is ({title.minimumWidth()} < {need})"
        )
        assert title.minimumWidth() > 140, (
            "the judged title kept the old fixed 140px floor (no widening)"
        )
        # Widening stays inside the 296px report column (scored value is short).
        assert row.minimumSizeHint().width() <= 296, (
            f"the widened title broke the W5 fit budget: {row.minimumSizeHint().width()}"
        )
    finally:
        ov._report_host.deleteLater()
