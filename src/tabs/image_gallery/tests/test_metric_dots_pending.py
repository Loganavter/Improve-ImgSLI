"""Metric-dot COUNT: pending affordance → measured-only (owner decision 2026-10-22).

Two phases, ONE decision (``ui/card/dots.metric_dots_for_item``):

* **Pending** — the requested axis set has no measurement at all (every record is
  a ``status="gap"``), so the card paints the whole requested set as the
  "still measuring" affordance. Camera therefore still shows its 8 neutral dots.
* **Measured** — the first axis that carries a value narrows the row to the
  MEASURED axes only: a gap stops being a dot, so a partially measured card
  counts exactly its real metrics and each landing axis adds one.

The grid card and the list row both read that one function's ``(colors, infos)``
(``ui/card.py`` / ``ui/list/card.py``), and the painters only place them — the
pending rule must not be re-derived per surface.
"""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRectF
from PySide6.QtGui import QImage, QPainter

from tabs.image_gallery.models import GalleryItem
from tabs.image_gallery.services.profile_judged import scorecard_axis_ids
from tabs.image_gallery.ui.card import build_gallery_card
from tabs.image_gallery.ui.card.dots import metric_dots_for_item
from tabs.image_gallery.ui.card.painters import _dots_overlay_painter
from tabs.image_gallery.ui.list.card import build_gallery_list_card
from tabs.image_gallery.ui.list.painters import _list_metric_dots_overlay


def _item(**overrides) -> GalleryItem:
    defaults = dict(path=Path("/gallery/a.png"), mtime_ns=1)
    defaults.update(overrides)
    return GalleryItem(**defaults)



def _analyzing(item: GalleryItem) -> GalleryItem:
    """Mark the item as ACTIVELY analyzing (the affordance phase, owner 2026-10-22)."""
    from tabs.image_gallery.models import ActivityPhase
    from tabs.image_gallery.services.activity import set_activity

    set_activity(item, ActivityPhase.QUEUED, "local")
    return item


def _paint_grid(card, width: int = 250, height: int = 170) -> None:
    image = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
    painter = QPainter(image)
    try:

        class _Ctx:
            widget = card
            rect = QRectF(0, 0, width, height)

        _dots_overlay_painter(painter, _Ctx(), None)
    finally:
        painter.end()


def _paint_list(card, width: int = 640, height: int = 64) -> None:
    image = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
    painter = QPainter(image)
    try:

        class _Ctx:
            widget = card
            rect = QRectF(0, 0, width, height)

        _list_metric_dots_overlay(painter, _Ctx())
    finally:
        painter.end()


def test_pending_item_paints_the_full_requested_axis_set() -> None:
    """No measurement yet → the whole asked set, neutral, exactly as before."""
    item = _analyzing(_item())
    requested = scorecard_axis_ids("camera")
    colors, infos = metric_dots_for_item(item, mode="camera", domain="algorithms")
    assert len(requested) == 8  # camera parity: the affordance never narrowed
    assert len(colors) == len(infos) == len(requested)
    assert all(score is None for _label, score in infos)
    assert all(color.alpha() == 120 for color in colors)


def test_pending_card_keeps_the_placeholder_geometry(qapp) -> None:
    """The pending phase is visually unchanged: one neutral dot per asked axis."""
    item = _analyzing(_item())
    card = build_gallery_card(item, parent=None, mode="camera", domain="algorithms")
    try:
        assert len(card._gallery_dot_colors) == len(scorecard_axis_ids("camera"))
        assert all(c.alpha() == 120 for c in card._gallery_dot_colors)
        _paint_grid(card)
        geometry = card._gallery_dot_geometry
        assert geometry is not None
        assert len(geometry["centers"]) == len(scorecard_axis_ids("camera"))
        # Right-aligned row on the filename line, as it always was.
        assert geometry["x_centers"] == tuple(sorted(geometry["x_centers"]))
        assert geometry["x_centers"][-1] < 250
    finally:
        card.deleteLater()


def test_one_measurement_narrows_the_dots_to_that_axis() -> None:
    item = _item(metrics={"sharpness": 320.0})  # 320 / 400 -> 80 %
    colors, infos = metric_dots_for_item(item, mode="camera", domain="algorithms")
    assert infos == (("Sharpness", 80),)
    assert len(colors) == 1
    assert colors[0].alpha() != 120  # a measured band, not the grey affordance


def test_partial_item_paints_only_the_measured_axes_in_registry_order() -> None:
    axes = scorecard_axis_ids("camera")
    item = _item(metrics={"sharpness": 320.0, "noise": 0.9})
    colors, infos = metric_dots_for_item(item, mode="camera", domain="algorithms")
    assert len(colors) == len(infos) == 2
    # Only the two measured axes, in the registry's own order (sharpness before
    # noise), with no grey placeholder reserving the gaps in between.
    assert infos == (("Sharpness", 80), ("Clean", 10))
    assert axes.index("sharpness") < axes.index("noise")
    assert all(score is not None for _label, score in infos)
    assert all(color.alpha() != 120 for color in colors)


def test_each_landing_axis_adds_one_dot() -> None:
    counts = []
    for metrics in (
        {"sharpness": 320.0},
        {"sharpness": 320.0, "exposure": 0.5},
        {"sharpness": 320.0, "exposure": 0.5, "noise": 0.9},
    ):
        colors, _infos = metric_dots_for_item(
            _item(metrics=dict(metrics)), mode="camera", domain="algorithms"
        )
        counts.append(len(colors))
    assert counts == [1, 2, 3]
    # The ask set never shrinks back to the placeholder after a measurement.
    assert counts != [len(scorecard_axis_ids("camera"))] * len(counts)


def test_grid_card_and_list_row_agree_on_the_measured_dots(qapp) -> None:
    item = _item(metrics={"sharpness": 320.0, "noise": 0.9})
    expected_colors, expected_infos = metric_dots_for_item(
        item, mode="camera", domain="algorithms"
    )
    card = build_gallery_card(item, parent=None, mode="camera", domain="algorithms")
    row = build_gallery_list_card(item, mode="camera", domain="algorithms")
    try:
        assert tuple(card._gallery_dot_colors) == expected_colors
        assert tuple(card._gallery_dot_infos) == expected_infos
        assert tuple(row._gallery_dot_colors) == expected_colors
        assert tuple(row._gallery_dot_infos) == expected_infos
        _paint_grid(card)
        _paint_list(row)
        assert card._gallery_dot_geometry is not None
        assert row._gallery_dot_geometry is not None
        assert len(card._gallery_dot_geometry["centers"]) == 2
        assert len(row._gallery_dot_geometry["centers"]) == 2
    finally:
        card.deleteLater()
        row.deleteLater()
