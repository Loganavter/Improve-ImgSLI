"""Quick look AI axis flags (plan-gallery-two-domain-axes W4).

Candidate flags and judgments render as text in the AI analysis block —
never as a measured metric row, never with a percentage. Measured rows are
unchanged by the presence of flags.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.widgets import Label as _QlLabel
from tabs.image_gallery.models import (
    AiAnalysisResult,
    AiAxisFlag,
    AnalysisStatus,
    GalleryItem,
    MetricKind,
    Mode,
)
from tabs.image_gallery.ui.quick_look import QuickLookOverlay


def _item(name: str, **kwargs) -> GalleryItem:
    return GalleryItem(path=Path(f"/gallery/{name}"), mtime_ns=1, **kwargs)


def _make_overlay(qtbot) -> QuickLookOverlay:
    parent = QWidget()
    qtbot.addWidget(parent)
    ov = QuickLookOverlay(parent)
    ov._parity_test_parent = parent
    return ov


def _show(overlay, item, series, mode=Mode.FIDELITY):
    owner = SimpleNamespace(
        state=SimpleNamespace(mode=mode, source_path=None, series=[list(series)], items=list(series)),
    )
    overlay.show_for(item, owner)
    parent = overlay._parity_test_parent
    parent.resize(1280, 800)
    parent.show()


def _analysed(name: str, flags, *, metrics=None) -> GalleryItem:
    analysis = AiAnalysisResult(
        description="",
        tags=(),
        model="test",
        analyzed_at_iso="2026-10-11T00:00:00",
        verdict="keep",
        verdict_reason="usable result",
        axis_flags=tuple(flags),
    )
    return _item(
        name,
        analysis=analysis,
        analysis_status=AnalysisStatus.DONE,
        metrics=dict(metrics or {}),
    )


def _metric_texts(ov) -> list[str]:
    return [lbl.text() for row in ov._metric_rows for lbl in row.findChildren(_QlLabel)]


def test_candidate_flag_renders_marker_without_number(qtbot):
    flag = AiAxisFlag(id="banding", label="banding", kind=MetricKind.CANDIDATE.value, note="faint steps")
    item = _analysed("c.png", [flag])
    ov = _make_overlay(qtbot)
    _show(ov, item, [item])
    tags = ov._analysis_tags.text()
    assert "possible banding" in tags
    assert "%" not in tags
    assert not any("banding" in t for t in _metric_texts(ov))
    ov.hide()


def test_judgment_flag_renders_ai_marker_without_number(qtbot):
    flag = AiAxisFlag(id="flag-for-review", label="invented texture", kind=MetricKind.JUDGMENT.value)
    item = _analysed("j.png", [flag])
    ov = _make_overlay(qtbot)
    _show(ov, item, [item])
    tags = ov._analysis_tags.text()
    assert "AI judgment: invented texture" in tags
    assert "%" not in tags
    ov.hide()


def test_flags_and_defect_chips_join(qtbot):
    from tabs.image_gallery.models import AiDefect

    flag = AiAxisFlag(id="halo", label="halo", kind=MetricKind.CANDIDATE.value)
    item = _analysed("d.png", [flag])
    item.analysis = AiAnalysisResult(
        description="",
        tags=(),
        model="test",
        analyzed_at_iso="2026-10-11T00:00:00",
        verdict="keep",
        verdict_reason="usable result",
        defects=(AiDefect(kind="over_smoothing", severity="mild"),),
        axis_flags=(flag,),
    )
    ov = _make_overlay(qtbot)
    _show(ov, item, [item])
    tags = ov._analysis_tags.text()
    assert "over smoothing (mild)" in tags
    assert "possible halo" in tags
    ov.hide()


def test_measured_rows_unchanged_by_flags(qtbot):
    metrics = {"sharpness": 150.0, "exposure": 0.5, "clipping": 2.6, "noise": 0.2}
    flag = AiAxisFlag(id="noise", label="grain", kind=MetricKind.CANDIDATE.value)

    plain = _item("p.png", metrics=dict(metrics))
    ov_plain = _make_overlay(qtbot)
    _show(ov_plain, plain, [plain], mode=Mode.CAMERA)
    before = _metric_texts(ov_plain)
    ov_plain.hide()

    flagged = _analysed("f.png", [flag], metrics=metrics)
    ov_flagged = _make_overlay(qtbot)
    _show(ov_flagged, flagged, [flagged], mode=Mode.CAMERA)
    after = _metric_texts(ov_flagged)
    ov_flagged.hide()

    assert before
    assert after == before
    assert any(t == "80%" for t in after)  # measured Clean unchanged


def test_unknown_kind_never_rendered(qtbot):
    flag = AiAxisFlag(id="sharpness", label="blur", kind=MetricKind.MEASURED.value)
    item = _analysed("u.png", [flag])
    ov = _make_overlay(qtbot)
    _show(ov, item, [item])
    assert "blur" not in ov._analysis_tags.text()
    ov.hide()


def test_candidate_flag_duplicating_a_defect_is_suppressed(qtbot):
    """A candidate already shown as a defect chip must not repeat itself."""
    from tabs.image_gallery.models import AiDefect

    flag = AiAxisFlag(id="halo", label="halo", kind=MetricKind.CANDIDATE.value)
    item = _analysed("dup.png", [flag])
    item.analysis = AiAnalysisResult(
        description="",
        tags=(),
        model="test",
        analyzed_at_iso="2026-10-11T00:00:00",
        verdict="keep",
        verdict_reason="usable result",
        defects=(AiDefect(kind="halo", severity="mild"),),
        axis_flags=(flag,),
    )
    ov = _make_overlay(qtbot)
    _show(ov, item, [item])
    tags = ov._analysis_tags.text()
    assert "halo (mild)" in tags
    assert "possible halo" not in tags
    ov.hide()
