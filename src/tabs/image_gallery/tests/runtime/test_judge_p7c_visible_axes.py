"""P7-C — the JUDGE's axes are VISIBLE, with their meaning and provenance.

P7-A let the model NAME 3..8 axes in free form, P7-B made the scorecard MEASURE
them and the ranker COMPARE them — but the user still saw only the registry
rows, so "why white balance, why aesthetics" stayed invisible. This wave puts
the judge's axes on the ONE read path and on the two surfaces that show an axis
(Quick Look rows, card dots), with the two honest labels the owner asked for.

Falsification story (what each test catches, and why it is red before):

- **(a)** a judge-named axis reaches the ROWS through ``analysis.read.read_axes``
  (one seam, not a parallel one) and the row shows the judge's NAME and its
  MEANING. Red before: ``rebuild_metrics`` iterated ``measured_axes_for`` (the
  registry half only) and read the AI domain without the profile, so the axis
  the judge named had no row at all.
- **(b)** an axis with NO measurement renders the "not measured" text, which is
  a real i18n key present in EVERY locale (not an empty row, not a zero). Red
  before: no row existed for the axis, so the loss was silent.
- **(c)** an axis that does NOT separate these variants (constant across the
  series, inside the noise floor) renders that reason. Red before: same missing
  row; and the floor now follows P7-B (the MEASURED within-item spread when the
  k draws carry it, the constant only as the single-draw fallback).
- **(d)** the registry half and the judge half are visually distinguishable by
  provenance, and a registry-only series renders EXACTLY as before (byte-identical
  row text when a judge entry is added — the P7-A
  ``test_without_a_profile_the_scorecard_is_byte_identical`` spirit).
- **(e)** the card dots show the judge's axes with their provenance and a dot
  colour that cannot be mistaken for a registry band, so the two instruments are
  never mixed into one unlabeled indicator.

Red-before evidence for every one of these was produced on a pre-change scratch
copy of ``HEAD`` (``git archive HEAD``) — see ``DONE.md``.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QApplication, QSizePolicy, QWidget

from tabs.image_gallery.analysis.read import read_axes
from tabs.image_gallery.models import AiAnalysisResult, AiAxisProposal, GalleryItem, Mode
from tabs.image_gallery.services.metric_profile import (
    MetricProfile,
    profile_for_mode,
)
from tabs.image_gallery.services.profile_judged import (
    PROVENANCE_JUDGE,
    PROVENANCE_LOCAL,
)
from tabs.image_gallery.ui.card.dots import metric_dots_for_item
from tabs.image_gallery.ui.quick_look import QuickLookOverlay
from sli_ui_toolkit.ui.widgets.atomic.text_labels import Label as _QlLabel  # internal: documented Label exception (queue task-text-unification-retirement-2026-10-21)
from sli_ui_toolkit.widgets import Text as _QlText

GALLERY = Path(__file__).resolve().parents[2]
I18N = GALLERY / "resources" / "i18n"

#: A judge-named axis: no local detector, no registry id — the normal answer.
FREE = AiAxisProposal(
    name="jpeg_noise",
    definition="8x8 block edges and mosquito noise; 0 = none visible, 100 = heavy",
    scale="0-100",
    direction="higher-is-better",
)


def _label_text(lbl) -> str:
    """Full label text (the painter elides, the widget keeps the string)."""
    try:
        getter = getattr(lbl, "get_original_text", None)
        if callable(getter):
            return str(getter())
    except Exception:
        pass
    return str(lbl.text())


def _qlabels(widget):
    return widget.findChildren(_QlLabel) + widget.findChildren(_QlText)


def _row_texts(overlay) -> list[str]:
    return [_label_text(lbl) for row in overlay._metric_rows for lbl in _qlabels(row)]


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
            text = _label_text(lbl)
            if text:
                out.append(text)
    return out


def _item(name: str, *, axes: dict | None = None, **metrics) -> GalleryItem:
    item = GalleryItem(path=Path(f"/gallery/{name}"), mtime_ns=1)
    item.metrics = dict(metrics)
    if axes is not None:
        item.analysis = AiAnalysisResult(
            description="",
            tags=(),
            model="m",
            analyzed_at_iso="t",
            axes=dict(axes),
        )
    return item


def _profile(*entries, axis_ids=("sharpness", "noise")) -> MetricProfile:
    return MetricProfile(
        axis_ids=axis_ids,
        mode="camera",
        source="vlm",
        axis_entries=tuple(entries),
    )


class _RowsStub:
    """Bare overlay surface for the row pipeline (no window, no layout)."""

    def __init__(self, item, profile, *, series=None, domain="ai"):
        self._metric_rows: list = []
        self._report_host = QWidget()
        self._metrics_host = self._report_host
        self._right_lay = None
        self._series_items = list(series or [item])
        self._current_idx = self._series_items.index(item)
        self._mode = Mode.CAMERA
        self._source_path = None
        self._owner = SimpleNamespace(
            _judgment_domain=domain,
            state=SimpleNamespace(
                mode=Mode.CAMERA, metric_profile=profile, judgment_domain=domain
            ),
        )


def _build_rows(qtbot, item, profile, *, series=None, domain="ai"):
    from tabs.image_gallery.ui.quick_look import metrics as m

    ov = _RowsStub(item, profile, series=series, domain=domain)
    qtbot.addWidget(ov._report_host)
    m.rebuild_metrics(ov, item, False, "CAMERA")
    return ov


# ---------------------------------------------------------------------------
# (a) the judge's axis reaches the rows ON THE READ PATH
# ---------------------------------------------------------------------------


def test_a_judge_named_axis_is_a_read_record_with_its_provenance():
    """The record carries the judge's NAME, its value and the P7-A token."""
    profile = _profile(FREE)
    item = _item(
        "read_record.png", axes={"sharpness": 80, FREE.name: 73}
    )

    record = read_axes(
        item, domain="ai", axes=(FREE.name,), profile=profile
    )[0]

    assert record.axis == FREE.name, "the axis is the judge's own name"
    assert record.value == 73.0 and record.status == "ok"
    assert record.producer == "vlm", "the model produced this number"
    assert record.provenance == PROVENANCE_JUDGE, (
        "the record must say WHO measured it (P7-A vocabulary), not leave the "
        "surface to guess from the name"
    )

    registry = read_axes(item, domain="ai", axes=("sharpness",), profile=profile)[0]
    assert registry.provenance == PROVENANCE_LOCAL, (
        "a registry axis a detector produces here is measured-locally"
    )
    # Without a profile the reader makes no claim (never a guess).
    assert read_axes(item, domain="ai", axes=("sharpness",))[0].provenance == ""


def test_a_judge_named_axis_reaches_the_rows_through_the_one_read_path(
    qtbot, monkeypatch
):
    profile = _profile(FREE)
    item = _item("read_rows.png", axes={"sharpness": 80, FREE.name: 73})

    calls: list[tuple] = []
    from tabs.image_gallery.analysis import read as read_module

    original = read_module.read_axes

    def _spy(item, *, domain, axes=None, profile=None):
        calls.append((tuple(axes or ()), profile))
        return original(item, domain=domain, axes=axes, profile=profile)

    monkeypatch.setattr(read_module, "read_axes", _spy)

    ov = _build_rows(qtbot, item, profile)
    try:
        assert calls, "the rows must read through analysis.read.read_axes"
        axes_seen, profile_seen = calls[-1]
        assert FREE.name in axes_seen, (
            "the judge's axis never reached the read path — rows asked for the "
            f"registry half only ({axes_seen})"
        )
        assert profile_seen is profile, "the reader needs the profile to label provenance"

        titles = _row_titles(ov)
        judged = [t for t in titles if FREE.name in t]
        assert judged, f"the judge's axis has no row: {titles}"
        assert FREE.definition in judged[0], (
            "the row must show the judge's MEANING, not just its name: "
            f"{judged[0]!r}"
        )
        assert any("%" in t for t in _row_texts(ov)), (
            "the measured value is missing from the rows"
        )
    finally:
        ov._report_host.deleteLater()


def test_the_trace_line_and_the_row_name_the_same_judged_axes(qtbot):
    """The trace's ``judged=`` half and the rows describe the same axes."""
    from tabs.image_gallery.services.metric_profile import format_profile

    profile = _profile(FREE)
    item = _item("trace.png", axes={"sharpness": 80, FREE.name: 73})
    ov = _build_rows(qtbot, item, profile)
    try:
        line = format_profile(profile)
        assert f"judged={FREE.name}~{FREE.direction}" in line
        assert any(FREE.name in t for t in _row_titles(ov)), (
            "the trace names a judged axis the rows do not show"
        )
    finally:
        ov._report_host.deleteLater()


# ---------------------------------------------------------------------------
# (b) no measurement -> "not measured", and the text is a real localized key
# ---------------------------------------------------------------------------


def test_an_unmeasured_judge_axis_says_not_measured(qtbot):
    profile = _profile(FREE)
    item = _item("unmeasured.png", axes={"sharpness": 80})  # judge axis unread

    ov = _build_rows(qtbot, item, profile)
    try:
        titles = _row_titles(ov)
        judged = [t for t in titles if FREE.name in t]
        assert judged, f"a judge axis with no reading vanished: {titles}"
        assert FREE.definition in judged[0]
        texts = _row_texts(ov)
        assert any("not measured" in t for t in texts), (
            f"an axis with no measurement must say so, not show a zero: {texts}"
        )
        assert not any(t.strip() == "0%" for t in texts), (
            "a gap must never read as a measured zero"
        )
    finally:
        ov._report_host.deleteLater()


def test_the_two_honest_labels_and_the_provenance_are_real_keys_in_every_locale():
    locales = sorted(p.parent.name for p in I18N.glob("*/image_gallery.json"))
    assert len(locales) >= 4, locales
    for key in (
        "not_measured",
        "axis_inside_noise",
        "axis_measured_locally",
        "axis_measured_by_judge",
    ):
        for locale in locales:
            data = json.loads(
                (I18N / locale / "image_gallery.json").read_text(encoding="utf-8")
            )
            value = data["image_gallery"]["quick_look"].get(key)
            assert isinstance(value, str) and value.strip(), (
                f"{key!r} is missing/empty in {locale} — the label the owner "
                "asked for must be localized, not an English literal"
            )


# ---------------------------------------------------------------------------
# (c) an axis that does not separate these variants says so
# ---------------------------------------------------------------------------


def test_a_judge_axis_inside_the_noise_floor_says_it_does_not_separate(qtbot):
    # jpeg_noise is constant across the series (70/70); noise moves 20 -> 80.
    a = _item("noise_a.png", axes={"noise": 20, FREE.name: 70})
    b = _item("noise_b.png", axes={"noise": 80, FREE.name: 70})
    profile = _profile(FREE, axis_ids=("noise",))

    ov = _build_rows(qtbot, a, profile, series=[a, b])
    try:
        texts = _row_texts(ov)
        reasons = [t for t in texts if "does not separate" in t]
        assert len(reasons) == 1, (
            "the judge's constant axis must render the reason, not a bare "
            f"number; rows were {texts}"
        )
        assert "0%" not in reasons[0], reasons[0]
        titles = _row_titles(ov)
        assert any(FREE.name in t for t in titles), (
            f"the reason row lost the judge's name: {titles}"
        )
        # The discriminating axis keeps its number.
        assert any(
            t.strip().rstrip("%").isdigit() for t in _row_texts(ov)
        ), f"the axis that DOES separate the series lost its number: {texts}"
    finally:
        ov._report_host.deleteLater()


def test_a_measured_noise_floor_is_the_one_the_rows_use(qtbot):
    """P7-B's MEASURED floor decides "inside noise" here too (never a second rule)."""
    a = _item("floor_a.png", axes={"noise": 20, FREE.name: 70})
    b = _item("floor_b.png", axes={"noise": 100, FREE.name: 86})
    # Within-item draws move jpeg_noise by 12; the constant floor (20) would
    # call a 16-point between-variant spread noise, the measured floor (12)
    # must not.
    a.analysis = AiAnalysisResult(
        description="", tags=(), model="m", analyzed_at_iso="t",
        axes={"noise": 20, FREE.name: 70},
        axis_samples=({"noise": 20, FREE.name: 64}, {"noise": 20, FREE.name: 76}),
    )
    b.analysis = AiAnalysisResult(
        description="", tags=(), model="m", analyzed_at_iso="t",
        axes={"noise": 100, FREE.name: 86},
        axis_samples=({"noise": 100, FREE.name: 80}, {"noise": 100, FREE.name: 92}),
    )
    profile = _profile(FREE, axis_ids=("noise",))

    from tabs.image_gallery.services.quality_read import axis_noise_floor

    assert axis_noise_floor("ai", samples=[a.analysis, b.analysis]) == 12.0
    assert axis_noise_floor("ai") == 20.0  # the single-draw constant
    ov = _build_rows(qtbot, a, profile, series=[a, b])
    try:
        # jpeg_noise moves 70 -> 86: above the measured 12 -> it DOES separate,
        # while the constant 20 would have suppressed it.
        assert not any("does not separate" in t for t in _row_texts(ov)), _row_texts(ov)
        assert any(
            FREE.name in t for t in _row_titles(ov)
        ), "the judge's axis must keep a measured row"
    finally:
        ov._report_host.deleteLater()


def test_a_judge_axis_renders_once_when_its_name_is_the_ai_only_composition_axis(
    qtbot,
):
    """The AI-only Composition row must not duplicate a judge-named one."""
    judged_composition = AiAxisProposal(
        name="composition",
        definition="framing and balance of the main subject; 0 = poor, 100 = excellent",
    )
    profile = MetricProfile(
        axis_ids=("sharpness",),
        mode="camera",
        source="vlm",
        axis_entries=(judged_composition,),
    )
    item = _item("composition.png", axes={"sharpness": 80, "composition": 66})
    item.analysis = AiAnalysisResult(
        description="",
        tags=(),
        model="m",
        analyzed_at_iso="t",
        axes={"sharpness": 80, "composition": 66},
        composition=66,
    )

    ov = _build_rows(qtbot, item, profile)
    try:
        titles = _row_titles(ov)
        composition_rows = [t for t in titles if "omposition" in t]
        assert len(composition_rows) == 1, (
            f"the same axis is rendered twice under two labels: {titles}"
        )
        assert judged_composition.definition in composition_rows[0], (
            "the judge's own wording must win over the registry label"
        )
    finally:
        ov._report_host.deleteLater()


def test_engine_records_carry_the_reader_provenance_token():
    """Engine-on: the record keeps its producer and gains the instrument token."""
    from engine.analysis.contracts import AxisValue

    record = AxisValue(
        axis=FREE.name,
        value=73.0,
        producer="vlm",
        status="ok",
    )
    profile = _profile(FREE)
    item = _item("engine.png")
    item.analysis_records = (record,)

    read = read_axes(
        item, domain="ai", axes=(FREE.name,), profile=profile
    )[0]

    assert read.provenance == PROVENANCE_JUDGE
    assert read.axis == FREE.name and read.value == 73.0
    assert read.producer == "vlm", "the producer id is never rewritten"
    assert record.provenance == "", (
        "the engine's own record is not mutated — the reader stamps a copy"
    )


def test_the_registry_half_is_byte_identical_when_a_judge_entry_is_added(qtbot):
    item = _item("regression.png", axes={"sharpness": 80, "noise": 90, FREE.name: 73})
    registry_only = MetricProfile(
        axis_ids=("sharpness", "noise"), mode="camera", source="vlm"
    )
    mixed = _profile(FREE, axis_ids=("sharpness", "noise"))

    base = _build_rows(qtbot, item, registry_only)
    try:
        base_texts = _row_texts(base)
    finally:
        base._report_host.deleteLater()
    with_judge = _build_rows(qtbot, item, mixed)
    try:
        mixed_texts = _row_texts(with_judge)
        assert len(mixed_texts) > len(base_texts), (
            "the judge's axis added no row — nothing became visible"
        )
        assert mixed_texts[: len(base_texts)] == base_texts, (
            "adding a judge axis edited the registry rows:\n"
            f"before={base_texts}\nafter={mixed_texts[: len(base_texts)]}"
        )
        # The two halves are labelled differently.
        registry_titles = [t for t in _row_titles(with_judge) if FREE.name not in t]
        judged_titles = [t for t in _row_titles(with_judge) if FREE.name in t]
        assert judged_titles, _row_titles(with_judge)
        assert "measured by the judge" in judged_titles[0]
        assert all("measured by the judge" not in t for t in registry_titles), (
            f"a registry row was labelled as the judge's: {registry_titles}"
        )
    finally:
        with_judge._report_host.deleteLater()


def test_a_registry_only_series_renders_the_same_rows_as_the_mode_mapping(qtbot):
    """No judge entry -> the row text is what it always was (both halves equal).

    The registry profile mirrors the mode mapping exactly (same ids, same
    order), so the rows must be identical to a profile-less render — the
    regression guard for the wave that adds a second axis half.
    """
    item = _item("mode_parity.png", axes={"sharpness": 80, "noise": 90})
    mode_axes = profile_for_mode("camera").axis_ids
    registry = MetricProfile(axis_ids=mode_axes, mode="camera", source="heuristic")
    ov_a = _build_rows(qtbot, item, registry)
    ov_b = _build_rows(qtbot, item, None)
    try:
        assert _row_texts(ov_a) == _row_texts(ov_b), (
            "a registry-only profile no longer renders like the mode mapping:\n"
            f"{_row_texts(ov_a)}\nvs\n{_row_texts(ov_b)}"
        )
    finally:
        ov_a._report_host.deleteLater()
        ov_b._report_host.deleteLater()


# ---------------------------------------------------------------------------
# (e) card dots: the judge's axes with their provenance
# ---------------------------------------------------------------------------


def test_card_dots_show_the_judge_axes_with_their_provenance():
    item = _item("dots.png", axes={"sharpness": 80, FREE.name: 73})
    profile = _profile(FREE)

    colors, infos = metric_dots_for_item(
        item, mode=Mode.CAMERA, domain="ai", profile=profile
    )

    labels = [label for label, _score in infos]
    # sharpness (measured locally) + the judge's jpeg_noise; the unmeasured
    # registry axis (noise) has no dot (owner 2026-10-22: gaps are suppressed
    # once anything in the set is measured).
    assert len(infos) == 2, labels  # sharpness, jpeg_noise
    judged = [(label, score) for label, score in infos if FREE.name in label]
    assert judged and judged[0][1] == 73
    assert "measured by the judge" in judged[0][0], (
        f"a judge dot is unlabeled — the two instruments are mixed: {labels}"
    )
    registry = [(label, score) for label, score in infos if label.startswith("Sharpness")]
    assert registry and "measured by the judge" not in registry[0][0]

    # The measured judge dot is not a severity band: its colour is the accent,
    # shared only with other judge dots.
    index = labels.index(judged[0][0])
    assert colors[index] != colors[0], (
        "the judge dot paints the same colour as a registry band — provenance "
        "is only in the tooltip"
    )


def test_an_unmeasured_judge_axis_reads_as_a_gap_only_while_nothing_is_measured():
    """Gap dots exist in the PENDING phase only (owner 2026-10-22).

    With one axis measured the dots narrow to the measured set, so the judge's
    unmeasured axis has no dot; with nothing measured the pending affordance
    still dots it and the tooltip still says "—" (the gap-label machinery the
    judge provenance owns is unchanged, it just only shows before any value).
    """
    profile = _profile(FREE)

    measured_item = _item("dots_gap.png", axes={"sharpness": 80})
    _colors, infos = metric_dots_for_item(
        measured_item, mode=Mode.CAMERA, domain="ai", profile=profile
    )
    assert [label for label, _score in infos] == ["Sharpness"], infos

    from tabs.image_gallery.tests._activity_fixtures import mark_analyzing

    pending_item = mark_analyzing(_item("dots_pending.png"))
    _colors, pending_infos = metric_dots_for_item(
        pending_item, mode=Mode.CAMERA, domain="ai", profile=profile
    )
    judged = [(label, score) for label, score in pending_infos if FREE.name in label]
    assert judged, pending_infos
    assert judged[0][1] is None, "an unscored judge axis must read as a gap"
    assert "measured by the judge" in judged[0][0]


# ---------------------------------------------------------------------------
# W5 fit: a long judge title elides, it never forces the panel wider
# ---------------------------------------------------------------------------


def _show_overlay(qtbot, item, series, *, profile, width=520):
    parent = QWidget()
    qtbot.addWidget(parent)
    overlay = QuickLookOverlay(parent)
    overlay._parity_test_parent = parent  # strong ref keeps the C++ tree alive
    owner = SimpleNamespace(
        _judgment_domain="ai",
        state=SimpleNamespace(
            mode=Mode.CAMERA,
            source_path=None,
            series=[list(series)],
            items=list(series),
            judgment_domain="ai",
            metric_profile=profile,
        ),
    )
    overlay.show_for(item, owner)
    parent.resize(width, 700)
    parent.show()
    QApplication.processEvents()
    return overlay, parent


def test_a_long_judge_title_elides_and_does_not_overflow_the_panel(qtbot):
    long_free = AiAxisProposal(
        name="chromatic_aberration_at_the_edges",
        definition=(
            "lateral colour fringing on high-contrast edges across the whole "
            "frame; 0 = invisible at 100% view, 100 = obvious purple/green rims"
        ),
        direction="lower-is-better",
    )
    profile = MetricProfile(
        axis_ids=("sharpness",), mode="camera", source="vlm", axis_entries=(long_free,)
    )
    item = _item(
        "long_title.png",
        axes={"sharpness": 80, long_free.name: 64},
    )
    overlay, parent = _show_overlay(qtbot, item, [item], profile=profile)
    try:
        host = overlay._report_host
        judged = [
            lbl
            for row in overlay._metric_rows
            for lbl in _qlabels(row)
            if long_free.name in _label_text(lbl)
        ]
        assert judged, "the long judge title did not render"
        title = judged[0]
        assert long_free.definition in _label_text(title), (
            "the full meaning must stay in the widget's text (paint elides, the "
            "data is not truncated)"
        )
        assert title.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Ignored, (
            "a long judge title must not contribute its full sizeHint to the "
            "fixed report column (W5 fit budget)"
        )
        assert title.sizeHint().width() > title.width(), (
            "the title is short enough to fit — the fixture no longer proves "
            "elision"
        )
        assert title.width() <= host.width(), (
            f"the title overflows the panel ({title.width()} > {host.width()})"
        )
    finally:
        overlay.hide()
        parent.deleteLater()
