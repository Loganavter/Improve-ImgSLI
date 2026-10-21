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

from tabs.image_gallery.models import AiAnalysisResult, GalleryItem, Mode
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


def _show(qtbot, item, series, *, mode=Mode.FIDELITY, domain="algorithms", profile=None):
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
            metric_profile=profile,
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
        self._owner = SimpleNamespace(
            state=SimpleNamespace(mode=Mode.FIDELITY, metric_profile=profile)
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
    ov._owner.state.metric_profile = MetricProfile(
        axis_ids=("sharpness", "exposure", "clipping", "noise"),
        mode="fidelity",
        source="vlm",
    )
    m.rebuild_metrics(ov, item, True, "FIDELITY")
    titles = _row_titles(ov)
    assert len(ov._metric_rows) == 4, titles
    assert any(t.startswith("Exposure") for t in titles), titles
    assert any(t.startswith("Highlight detail") for t in titles), titles
