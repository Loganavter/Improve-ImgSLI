"""A judge-named axis reaches the user under its HUMAN name, from the model.

Live defect (owner screenshot 2026-10-27, Quick Look):

    line_crispness — sharpness …
    denoise_smoothness — resi…
    color_saturation — vividnes…

Three failures in one row: the header is the machine snake_case id, the
definition is what gets elided (so the reader loses the meaning AND reads an id),
and the model was never asked for a human name in the first place — the reply
contract itself demanded ``"<snake_case id>"``.

The fix has one owner per layer, and each is pinned here:

- **contract** — an axis carries ``label``: a short human-readable name in the UI
  language (``AiAxisProposal.label``, ``""`` = the pre-label behaviour);
- **prompt** — the scorecard asks for it explicitly, and says "not the id";
- **cache** — the pin and the scorecard payload carry the label through a
  round-trip; a record written before the field loads as ``label=""``;
- **display** — one reader (``profile_judged.axis_display_name``) answers the row
  header: the label, else the id with ``_`` → space. The definition moves to the
  row TOOLTIP (it is the model's own text, not a header), and the header is
  elided only by the width the column actually has.

Red before (``63eae8d``): ``AiAxisProposal`` has no ``label`` field at all (the
constructor raises ``TypeError``), ``parse_proposals``/``parse_axis_choices`` keep
nothing of the sort, the row header is ``name — definition · provenance`` (an id
plus a definition cut to "…"), and ``profile_judged.axis_display_name`` does not
exist.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from PySide6.QtWidgets import QWidget

from tabs.image_gallery.models import AiAnalysisResult, AiAxisProposal, GalleryItem, Mode
from tabs.image_gallery.services import ai_cache
from tabs.image_gallery.services.ai_client.prompt import build_prompt
from tabs.image_gallery.services.axis_choice import parse_axis_choices
from tabs.image_gallery.services.axis_proposal import parse_proposals
from tabs.image_gallery.services.metric_profile import MetricProfile
from tabs.image_gallery.services.profile_cache import ProfileCache
from tabs.image_gallery.services.profile_judged import axis_display_name
from sli_ui_toolkit.ui.widgets.atomic.text_labels import Label as _QlLabel  # internal: documented Label exception (queue task-text-unification-retirement-2026-10-21)
from sli_ui_toolkit.widgets import Text as _QlText

#: The owner's first row, with the name the model SHOULD have answered with.
LABELED = AiAxisProposal(
    name="line_crispness",
    label="Line crispness",
    definition="separated hairlines and micro-contrast; 0 = mush, 100 = crisp",
)
#: A pre-label entry: no human name, so the id is all there is.
UNLABELED = AiAxisProposal(
    name="line_crispness",
    definition="separated hairlines and micro-contrast; 0 = mush, 100 = crisp",
)


def _profile(*entries, axis_ids=("sharpness",)) -> MetricProfile:
    return MetricProfile(
        axis_ids=axis_ids,
        mode="camera",
        source="vlm",
        axis_entries=tuple(entries),
    )


# ---------------------------------------------------------------------------
# the one reader of a display name
# ---------------------------------------------------------------------------


def test_the_display_name_is_the_model_label_when_it_gave_one():
    profile = _profile(LABELED)
    assert axis_display_name(LABELED.name, profile=profile) == "Line crispness"


def test_without_a_label_the_id_is_read_as_words_not_as_an_id():
    profile = _profile(UNLABELED)
    assert axis_display_name(UNLABELED.name, profile=profile) == "line crispness", (
        "a pre-label entry must fall back to the id with '_' → ' ', never the "
        "raw machine id"
    )
    # An axis the profile never named (a registry id, a trace read) is still
    # answered — the reader is total, not judge-only.
    assert axis_display_name("detail_gain", profile=profile) == "detail gain"
    assert axis_display_name("detail_gain", profile=None) == "detail gain"


def test_the_display_name_never_raises():
    class _Junk:
        @property
        def name(self):  # pragma: no cover - exercised through the reader
            raise RuntimeError("boom")

        @property
        def label(self):  # pragma: no cover
            raise RuntimeError("boom")

    junk = SimpleNamespace(axis_entries=(_Junk(),), axis_ids=())
    for axis in ("", None, 7, "line_crispness"):
        text = axis_display_name(axis, profile=junk)
        assert isinstance(text, str)


# ---------------------------------------------------------------------------
# the reply contract keeps the label (scorecard AND the axis selector)
# ---------------------------------------------------------------------------


def test_a_scorecard_proposal_keeps_its_label_un_normalized():
    accepted, refusals = parse_proposals(
        [
            {
                "name": "line_crispness",
                "label": "  Line crispness  ",
                "definition": "separated hairlines; 0 = mush, 100 = crisp",
                "scale": "0-100",
                "score": 74,
            }
        ]
    )
    assert refusals == ()
    assert accepted[0].label == "Line crispness", (
        "the label is display text: trimmed, kept in the model's own words, never "
        f"normalized into an id; got {accepted[0].label!r}"
    )
    assert accepted[0].name == "line_crispness", "the id stays the stable key"


def test_a_selector_pick_keeps_its_label():
    choices = parse_axis_choices(
        [
            {
                "name": "line_crispness",
                "label": "Line crispness",
                "definition": "separated hairlines; 0 = mush, 100 = crisp",
                "scale": "0-100",
            }
        ]
    )
    assert [entry.name for entry in choices.entries] == ["line_crispness"]
    assert choices.entries[0].label == "Line crispness"
    # A bare id carries no label — the old answer shape keeps working.
    bare = parse_axis_choices(["glow_bloom"])
    assert bare.entries[0].label == ""


def test_the_scorecard_prompt_asks_for_a_human_label_and_says_what_it_is_not():
    text = build_prompt(
        "camera",
        profile=MetricProfile(mode="camera", source="vlm", axis_ids=("noise",)),
    )
    assert '"label"' in text, f"the reply schema never asks for a label: {text}"
    lowered = text.lower()
    assert "human-readable" in lowered or "human readable" in lowered, (
        "the prompt must say WHAT kind of name it wants"
    )
    assert "not the id" in lowered or "not an id" in lowered, (
        "the prompt must say the label is not the snake_case id — otherwise the "
        "model answers the id again (the defect this test exists for)"
    )


# ---------------------------------------------------------------------------
# the caches carry it (a HIT must show what a MISS shows)
# ---------------------------------------------------------------------------


def test_the_profile_pin_round_trips_the_label(tmp_path):
    cache = ProfileCache(tmp_path)
    profile = _profile(LABELED)
    cache.put("k", profile)
    stored = cache.get("k")
    assert stored == profile
    assert stored.axis_entries[0].label == "Line crispness", (
        "a re-opened folder must not lose the human name the model gave"
    )


def test_a_pinned_record_written_before_the_label_reads_as_no_label(tmp_path):
    cache = ProfileCache(tmp_path)
    cache.put("k", _profile(UNLABELED))
    path = next(Path(tmp_path).iterdir())
    record = json.loads(path.read_text(encoding="utf-8"))
    for row in record["axis_entries"]:
        row.pop("label", None)  # the pre-label format
    path.write_text(json.dumps(record), encoding="utf-8")

    stored = cache.get("k")
    assert stored is not None, "an old pin must still be readable"
    assert stored.axis_entries[0].label == ""


def test_the_scorecard_cache_round_trips_the_label(tmp_path, monkeypatch):
    monkeypatch.setattr(ai_cache, "ai_cache_dir", lambda: tmp_path)
    identity = ai_cache.analysis_cache_identity(
        None, mode="camera", profile=("sharpness",)
    )
    path = Path("/gallery/label.png")
    result = AiAnalysisResult(
        description="",
        tags=(),
        model="m",
        analyzed_at_iso="t",
        axes={"sharpness": 80},
        axis_proposals=(AiAxisProposal(name="halation", label="Halation", score=61),),
        axis_entries=(LABELED,),
    )
    ai_cache.save_analysis(path, 1, result, identity)

    loaded = ai_cache.load_cached_analysis(path, 1, identity)
    assert loaded is not None
    assert loaded.axis_entries[0].label == "Line crispness", (
        "a HIT lost the label a MISS would carry"
    )
    assert loaded.axis_proposals[0].label == "Halation"


def test_a_scorecard_record_written_before_the_label_reads_as_no_label(tmp_path, monkeypatch):
    monkeypatch.setattr(ai_cache, "ai_cache_dir", lambda: tmp_path)
    identity = ai_cache.analysis_cache_identity(
        None, mode="camera", profile=("sharpness",)
    )
    path = Path("/gallery/legacy.png")
    result = AiAnalysisResult(
        description="",
        tags=(),
        model="m",
        analyzed_at_iso="t",
        axes={"sharpness": 80},
        axis_entries=(UNLABELED,),
    )
    ai_cache.save_analysis(path, 1, result, identity)
    stored_path = next(Path(tmp_path).iterdir())
    data = json.loads(stored_path.read_text(encoding="utf-8"))
    for key in ("axis_entries", "axis_proposals"):
        for row in data.get(key, []) or []:
            row.pop("label", None)
    stored_path.write_text(json.dumps(data), encoding="utf-8")

    loaded = ai_cache.load_cached_analysis(path, 1, identity)
    assert loaded is not None
    assert loaded.axis_entries[0].label == ""


# ---------------------------------------------------------------------------
# the row header: the human name, with the definition in the tooltip
# ---------------------------------------------------------------------------


def _row_items(widget):
    return widget.findChildren(_QlLabel) + widget.findChildren(_QlText)


def _label_text(lbl) -> str:
    try:
        getter = getattr(lbl, "get_original_text", None)
        if callable(getter):
            return str(getter())
    except Exception:
        pass
    return str(lbl.text())


def _titles(overlay) -> list[str]:
    from PySide6.QtCore import Qt

    out: list[str] = []
    for row in overlay._metric_rows:
        for lbl in _row_items(row):
            try:
                if bool(lbl.alignment() & Qt.AlignmentFlag.AlignRight):
                    continue
            except Exception:
                pass
            text = _label_text(lbl)
            if text:
                out.append(text)
    return out


class _RowsStub:
    """Bare overlay surface for the row pipeline (no window, no layout)."""

    def __init__(self, item: GalleryItem, profile) -> None:
        self._metric_rows: list = []
        self._report_host = QWidget()
        self._metrics_host = self._report_host
        self._right_lay = None
        self._series_items = [item]
        self._current_idx = 0
        self._mode = Mode.CAMERA
        self._source_path = None
        self._owner = SimpleNamespace(
            _judgment_domain="ai",
            state=SimpleNamespace(mode=Mode.CAMERA, ai_profile=profile),
        )


def _build(qtbot, *, entry, axes: dict) -> _RowsStub:
    from tabs.image_gallery.ui.quick_look import metrics as m

    item = GalleryItem(path=Path("/gallery/label_row.png"), mtime_ns=1)
    item.analysis = AiAnalysisResult(
        description="", tags=(), model="m", analyzed_at_iso="t", axes=dict(axes)
    )
    ov = _RowsStub(item, _profile(entry))
    qtbot.addWidget(ov._report_host)
    m.rebuild_metrics(ov, item, False, "CAMERA")
    return ov


def test_the_row_header_is_the_human_label_and_the_tooltip_has_the_definition(qtbot):
    ov = _build(qtbot, entry=LABELED, axes={"sharpness": 80, LABELED.name: 74})
    try:
        titles = _titles(ov)
        assert "Line crispness" in titles, (
            f"the judge's row still shows the machine id: {titles}"
        )
        assert not any(t.startswith("line_crispness") for t in titles), titles
        assert not any(LABELED.definition in t for t in titles), (
            "the definition still rides in the header instead of the tooltip — "
            f"that is what got cut to '…': {titles}"
        )
        tooltips = [row.toolTip() for row in ov._metric_rows]
        assert any(LABELED.definition in tip for tip in tooltips), (
            f"the meaning is not in any row tooltip: {tooltips}"
        )
    finally:
        ov._report_host.deleteLater()


def test_a_pre_label_row_falls_back_to_the_id_as_words(qtbot):
    ov = _build(qtbot, entry=UNLABELED, axes={"sharpness": 80, UNLABELED.name: 74})
    try:
        titles = _titles(ov)
        assert "line crispness" in titles, (
            f"the fallback header is not the id read as words: {titles}"
        )
        assert not any(t.startswith("line_crispness") for t in titles), titles
        assert any(
            UNLABELED.definition in row.toolTip() for row in ov._metric_rows
        ), "the old entry's definition must still be reachable in the tooltip"
    finally:
        ov._report_host.deleteLater()
