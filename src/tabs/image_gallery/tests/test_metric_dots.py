"""Per-mode METRIC-AXIS dots + per-dot hover tooltip (gal-metric-dots).

Product decision: the gallery quality dots are one dot per measured axis for
the current mode (camera 8 / fidelity 14 / batch_synthetic 7), valued from the
current domain read and colored by ``score_band``. The old artifact triple is
gone.
"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QRectF
from PySide6.QtGui import QImage, QPainter

from tabs.image_gallery.models import GalleryItem
from tabs.image_gallery.services.metric_scores import spec_for
from tabs.image_gallery.services.rank_fusion import measured_axes_for
from tabs.image_gallery.ui.card.dot_tooltip import dot_tooltip_text_at
from tabs.image_gallery.ui.card.dots import (
    DOT_PITCH,
    _severity_color,
    dot_tooltip_text,
    layout_dots,
    metric_dots_for_item,
)
from tabs.image_gallery.ui.card.painters import _dots_overlay_painter
from tabs.image_gallery.ui.list.card import build_gallery_list_card
from tabs.image_gallery.ui.list.painters import _list_metric_dots_overlay


def _item(**overrides) -> GalleryItem:
    defaults = dict(path=Path("/gallery/a.png"), mtime_ns=1)
    defaults.update(overrides)
    return GalleryItem(**defaults)


@pytest.mark.parametrize("mode", ["camera", "fidelity", "batch_synthetic", None])
def test_dot_count_matches_measured_axes(mode) -> None:
    item = _item()
    colors, infos = metric_dots_for_item(item, mode=mode)
    axes = measured_axes_for(mode)
    assert len(colors) == len(axes)
    assert len(infos) == len(axes)
    # Registry report order + labels.
    assert [label for label, _score in infos] == [
        (spec_for(axis).label if spec_for(axis) else axis) for axis in axes
    ]


def test_known_score_maps_to_the_right_band_color() -> None:
    item = _item(metrics={"sharpness": 320.0})  # 320 / 400 -> 80 %
    axes = measured_axes_for("camera")
    idx = axes.index("sharpness")
    colors, infos = metric_dots_for_item(item, mode="camera", domain="algorithms")
    assert infos[idx] == ("Sharpness", 80)
    assert str(colors[idx].name()).lower() == _severity_color("clean").name().lower()

    bad = _item(metrics={"sharpness": 40.0})  # 10 % -> bad
    colors, infos = metric_dots_for_item(bad, mode="camera", domain="algorithms")
    assert infos[idx] == ("Sharpness", 10)
    assert str(colors[idx].name()).lower() == _severity_color("flagged").name().lower()


def test_unscored_axis_is_muted_and_has_no_number() -> None:
    item = _item()
    colors, infos = metric_dots_for_item(item, mode="camera")
    assert all(score is None for _label, score in infos)
    neutral = _severity_color("clean")
    assert all(color.alpha() == 120 for color in colors)
    assert all(str(color.name()).lower() != neutral.name().lower() for color in colors)
    assert dot_tooltip_text(infos[0]) == f"{infos[0][0]}: —"


def test_tooltip_string_is_label_colon_percent() -> None:
    assert dot_tooltip_text(("Резкость", 68)) == "Резкость: 68%"
    assert dot_tooltip_text(("Sharpness", 0)) == "Sharpness: 0%"
    assert dot_tooltip_text(("Sharpness", None)) == "Sharpness: —"


def test_label_uses_tab_translator_with_registry_fallback() -> None:
    def tr(key: str, default: str) -> str:
        if key == "image_gallery.metric.sharpness":
            return "Резкость"
        return default

    axes = measured_axes_for("camera")
    _colors, infos = metric_dots_for_item(_item(), mode="camera", translate=tr)
    idx = axes.index("sharpness")
    assert infos[idx][0] == "Резкость"
    # An untranslated axis still reads the registry label, never the raw id.
    other = next(i for i, axis in enumerate(axes) if axis != "sharpness")
    assert infos[other][0] == spec_for(axes[other]).label


def test_hit_test_maps_cursor_x_to_the_nearest_dot() -> None:
    card = SimpleNamespace(
        _gallery_dot_geometry={
            "x_centers": (100.0, 114.0),
            "pitch": 14.0,
            "infos": (("A", 80), ("B", None)),
            "y_center": 40.0,
        }
    )
    assert dot_tooltip_text_at(card, 100) == "A: 80%"
    assert dot_tooltip_text_at(card, 112) == "B: —"  # nearest center wins
    assert dot_tooltip_text_at(card, 60) is None  # off the dots
    card._gallery_dot_geometry = None
    assert dot_tooltip_text_at(card, 100) is None


def test_layout_dots_wraps_and_keeps_the_full_pitch() -> None:
    # Two columns' worth of width -> 14 dots wrap into 7 full rows.
    centers = layout_dots(14, 200.0, 40.0, float(DOT_PITCH * 2))
    assert len(centers) == 14
    rows: dict[float, list[float]] = {}
    for cx, cy in centers:
        rows.setdefault(round(cy, 3), []).append(cx)
    assert len(rows) >= 2  # wrapped, not one clipped/shrunk line
    row_ys = sorted(rows)
    assert row_ys == sorted(row_ys)  # monotonic top-to-bottom row y
    for ys in row_ys:
        xs = sorted(rows[ys])
        # Every row is right-aligned to the block edge...
        assert xs[-1] == pytest.approx(200.0)
        # ...and never shrunk below the normal pitch.
        for left, right in zip(xs, xs[1:]):
            assert right - left == pytest.approx(float(DOT_PITCH))


def test_layout_dots_wide_width_stays_one_row() -> None:
    centers = layout_dots(14, 300.0, 40.0, 1000.0)
    assert len(centers) == 14
    assert len({round(cy, 3) for _cx, cy in centers}) == 1
    xs = sorted(cx for cx, _cy in centers)
    assert xs[-1] == pytest.approx(300.0)
    assert all(cy == pytest.approx(40.0) for _cx, cy in centers)
    for left, right in zip(xs, xs[1:]):
        assert right - left == pytest.approx(float(DOT_PITCH))


def test_layout_dots_centers_are_vertically_centered() -> None:
    centers = layout_dots(4, 200.0, 40.0, float(DOT_PITCH))  # 1 col -> 4 rows
    ys = sorted({round(cy, 3) for _cx, cy in centers})
    assert ys[0] < 40.0 < ys[-1]  # block extends up and down around y_center
    assert (ys[0] + ys[-1]) / 2.0 == pytest.approx(40.0)


def test_hit_test_resolves_by_x_and_y() -> None:
    # 2 rows: row 0 at y=40, row 1 at y=54 (one DOT_PITCH below).
    centers = ((100.0, 40.0), (114.0, 40.0), (100.0, 54.0))
    card = SimpleNamespace(
        _gallery_dot_geometry={
            "centers": centers,
            "pitch": float(DOT_PITCH),
            "infos": (("A", 80), ("B", None), ("C", 55)),
        }
    )
    # A point on a second-row dot resolves to that dot, not the x-nearest one.
    assert dot_tooltip_text_at(card, 100, 54) == "C: 55%"
    assert dot_tooltip_text_at(card, 114, 40) == "B: —"
    # A point BETWEEN the rows keeps the nearest dot's tooltip: the hover cell
    # tiles the block, so the gap must not revert to the card name.
    assert dot_tooltip_text_at(card, 100, 47) in ("A: 80%", "C: 55%")
    # A point genuinely OUTSIDE the block still resolves to nothing.
    assert dot_tooltip_text_at(card, 400, 40) is None


def test_grid_painter_stashes_geometry_for_every_dot(qapp) -> None:
    item = _item(metrics={"sharpness": 320.0})
    from tabs.image_gallery.ui.card import build_gallery_card

    card = build_gallery_card(item, parent=None, mode="camera")
    image = QImage(250, 170, QImage.Format.Format_ARGB32_Premultiplied)
    painter = QPainter(image)
    try:

        class _Ctx:
            widget = card
            rect = QRectF(0, 0, 250, 170)

        _dots_overlay_painter(painter, _Ctx(), None)
    finally:
        painter.end()
    geometry = card._gallery_dot_geometry
    axes = measured_axes_for("camera")
    assert geometry is not None
    assert len(geometry["centers"]) == len(axes)
    assert len(geometry["x_centers"]) == len(axes)
    assert len(geometry["infos"]) == len(axes)
    assert geometry["x_centers"] == tuple(sorted(geometry["x_centers"]))
    card.deleteLater()


def test_list_row_has_the_same_metric_dots(qapp) -> None:
    item = _item(metrics={"sharpness": 320.0})
    card = build_gallery_list_card(item, mode="camera", domain="algorithms")
    axes = measured_axes_for("camera")
    assert len(card._gallery_dot_colors) == len(axes)
    assert len(card._gallery_dot_infos) == len(axes)
    assert card._gallery_dot_infos == metric_dots_for_item(
        item, mode="camera", domain="algorithms"
    )[1]

    image = QImage(640, 64, QImage.Format.Format_ARGB32_Premultiplied)
    painter = QPainter(image)
    try:

        class _Ctx:
            widget = card
            rect = QRectF(0, 0, 640, 64)

        _list_metric_dots_overlay(painter, _Ctx())
    finally:
        painter.end()
    geometry = card._gallery_dot_geometry
    assert geometry is not None
    assert len(geometry["centers"]) == len(axes)
    assert len(geometry["x_centers"]) == len(axes)
    # Right-aligned inside the row's meta region.
    assert all(x < 640 for x in geometry["x_centers"])
    card.deleteLater()


def test_dot_to_dot_mouse_move_refreshes_instantly(qtbot) -> None:
    """Moving dot→dot inside ONE card refreshes the bubble with no re-delay.

    Qt sends no ``Enter`` within a single widget and re-delays the next
    ``ToolTip`` event, so the per-dot filter refreshes on ``MouseMove`` while
    the ``PathTooltip`` session is live.
    """
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QWidget

    from sli_ui_toolkit.ui.widgets.atomic.tooltips import PathTooltip
    from tabs.image_gallery.ui.card.dot_tooltip import _CardDotTooltipFilter

    def _move(x: float, y: float) -> QMouseEvent:
        return QMouseEvent(
            QEvent.Type.MouseMove,
            QPointF(x, y),
            QPointF(x, y),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )

    w = QWidget()
    qtbot.addWidget(w)
    w._gallery_dot_geometry = {  # two dots, two rows
        "centers": ((100.0, 10.0), (100.0, 24.0)),
        "pitch": 14.0,
        "infos": (("Резкость", 68), ("Экспозиция", 74)),
    }
    filt = _CardDotTooltipFilter(w)
    pt = PathTooltip.get_instance()
    pt._session_until_ms = pt._now_ms() + 5000.0  # a tooltip was just shown
    assert filt.eventFilter(w, _move(100, 24)) is False  # never swallowed
    assert filt._shown_text == "Экспозиция: 74%"
    # Off a dot the cache clears so the next dot re-shows.
    filt.eventFilter(w, _move(5, 5))
    assert filt._shown_text is None
