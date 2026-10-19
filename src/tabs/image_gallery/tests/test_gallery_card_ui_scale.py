"""The gallery grid CARD scales as ONE unit with UiScale.

Owner report 2026-10-19 (plan-live-appearance-fixes-2026-10-19): at UI scale
1.5 the gallery grid card came out cramped — the outer card grew (the toolkit
``Button`` scales ``size=`` internally) but the **thumbnail box**, the
**filename row zone** and the **metric dots** stayed at their 1.0 px, so the
card read smaller than the surrounding chrome. The series header is fine.

Root cause (measured, not assumed — see the measurement table in the lane's
DONE.md): the card's ``CustomSplit`` rect fns (``ui/card.py``) returned RAW
design-px literals (``QRectF(8, 8, 234, 110)`` / ``QRectF(0, 118, w, 52)``)
while ``rect_fns`` receive the card's ACTUAL rect — so the cover/text boxes
never followed the factor. The nearest WORKING sibling is the list row
(``ui/list/card.py``), whose rect fns resolve ``scaled_px`` and derive widths
from ``r`` at USE time. The same raw literals sat in the painted chrome
(metric dots, rank badge, hover bar, activity box).

Design px must be resolved at USE time (never a construction-time cache), and
``Button`` scales ``size=`` / ``corner_radius=`` / ``content_padding=`` /
``ButtonRegion.corner_radii`` internally exactly once — those stay design px;
passing a pre-scaled value there would double-scale (factor^2, the sibling
toolbar bug in ``tests/test_gallery_switch_ui_scale.py``).

At factor 1.0 every assertion is a no-op, so the suite is green before and
after on the default factor — it is red only at factor > 1.0 pre-fix.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap

from sli_ui_toolkit.managers import UiScale, scaled_px

from core.evidence.journal import record_evidence, reset_journal, verdict
from tabs.image_gallery.models import GalleryItem
from tabs.image_gallery.ui.card import GALLERY_CARD_H, GALLERY_CARD_W, build_gallery_card
from tabs.image_gallery.ui.card.dots import DOT_DIAMETER, DOT_PITCH
from tabs.image_gallery.ui.card.painters import _dots_overlay_painter
from tests.helpers.drain_until_stable import drain_until_stable

#: Design px of the preview (thumbnail) box inside the 250x170 card.
_COVER = (8, 8, 234, 110)
#: Design px of the bottom text zone: left, top, height (width follows the card).
_TEXT_TOP, _TEXT_H = 118, 52


@pytest.fixture(autouse=True)
def _restore_ui_scale():
    """Never leak a parametrized factor into later suites (process singleton)."""
    reset_journal()
    yield
    UiScale.get_instance().set_factor(1.0)


def _item() -> GalleryItem:
    return GalleryItem(path=Path("/gallery/a.png"), mtime_ns=1)


def _card(factor: float):
    UiScale.get_instance().set_factor(factor)
    return build_gallery_card(_item(), parent=None, mode="camera")


def _rect_ints(rect) -> tuple[int, int, int, int]:
    return (int(rect.x()), int(rect.y()), int(rect.width()), int(rect.height()))


def _snapshot(factor: float) -> dict:
    """Build the REAL card at *factor*, read every card number, then delete it.

    Each card is read at the factor it was built with and destroyed before the
    next factor is set: an ALIVE toolkit Button re-derives its ``size=`` live on
    a factor change, so keeping two cards around would compare stale snapshots.
    """
    card = _card(factor)
    try:
        card.render(QPixmap(card.size()))
        geometry = card._gallery_dot_geometry or {}
        centers = geometry.get("centers") or ()
        step = centers[1][0] - centers[0][0] if len(centers) >= 2 else 0.0
        return {
            "size": (card.width(), card.height()),
            "cover": _rect_ints(card.region_rect("cover")),
            "text": _rect_ints(card.region_rect("text")),
            "content_padding": tuple(card.getContentPadding()),
            "dot_pitch": float(geometry.get("pitch") or 0.0),
            "dot_step": float(step),
        }
    finally:
        card.deleteLater()


def _fake_widget(colors) -> SimpleNamespace:
    """Minimal widget surface the dots/badge painter reads (grid + list parity).

    Two regions: the painter's text-region math needs ``len(regions) >= 2``,
    exactly like the real card (bg + cover + text).
    """
    art_region = SimpleNamespace(id="art", weight=1.0, rows=None)
    text_region = SimpleNamespace(
        id="text",
        weight=1.0,
        rows=[SimpleNamespace(size=12, weight="normal")],
    )
    return SimpleNamespace(
        _gallery_badge=None,
        _gallery_badge_style=None,
        _gallery_dot_colors=list(colors),
        _gallery_dot_infos=tuple(("axis", None) for _ in colors),
        _hover_blue_bar=False,
        regions=lambda: [art_region, text_region],
        getContentPadding=lambda: (0, 0, 0, 0),
        is_bg_locked=lambda: False,
    )


_WHITE = QColor(255, 255, 255)


def _paint_overlay(factor: float, widget: SimpleNamespace) -> tuple[QImage, int]:
    UiScale.get_instance().set_factor(factor)
    w, h = int(scaled_px(GALLERY_CARD_W)), int(scaled_px(GALLERY_CARD_H))
    image = QImage(w, h, QImage.Format.Format_ARGB32)
    image.fill(_WHITE)
    painter = QPainter(image)
    try:
        _dots_overlay_painter(
            painter, SimpleNamespace(widget=widget, rect=QRectF(0, 0, w, h)), None
        )
    finally:
        painter.end()
    return image, h


def _ink_run(image: QImage, cx: float, cy: float) -> int:
    """Width of the contiguous non-background run through ``(cx, cy)``."""
    y = int(round(cy))
    left = int(round(cx))
    while left > 0 and image.pixelColor(left - 1, y) != _WHITE:
        left -= 1
    right = int(round(cx))
    while right < image.width() - 1 and image.pixelColor(right + 1, y) != _WHITE:
        right += 1
    return right - left + 1


def test_card_outer_size_scales_once_not_squared(qapp) -> None:
    base, scaled = _snapshot(1.0), _snapshot(1.5)
    assert base["size"] == (GALLERY_CARD_W, GALLERY_CARD_H)
    assert scaled["size"] == (
        int(scaled_px(GALLERY_CARD_W)),
        int(scaled_px(GALLERY_CARD_H)),
    )
    assert scaled["size"] == (375, 255)
    # factor^2 would be 562x382 (the sibling toolbar double-scale bug).
    assert scaled["size"][0] not in (GALLERY_CARD_W, 562)


def test_toolkit_managed_design_px_stay_design_px(qapp) -> None:
    """``content_padding``/radius are scaled by the toolkit — never pre-scale them.

    ``Button`` resolves ``content_padding`` and ``ButtonRegion.corner_radii``
    internally (verified: a 20px padded label paints at dx 21 @1.0 and 32 @1.5).
    Passing ``scaled_px(...)`` here would double-scale — the invariant this
    test pins.
    """
    assert _snapshot(1.5)["content_padding"] == (8.0, 8.0, 8.0, 8.0)


def test_cover_box_is_the_thumbnail_and_scales_once(qapp) -> None:
    """The reported bug: the preview box stayed at 1.0 px on a 1.5 card."""
    base, scaled = _snapshot(1.0), _snapshot(1.5)
    assert base["cover"] == _COVER
    assert scaled["cover"] == (
        int(scaled_px(_COVER[0])),
        int(scaled_px(_COVER[1])),
        int(scaled_px(_COVER[2])),
        int(scaled_px(_COVER[3])),
    )
    assert scaled["cover"] == (12, 12, 351, 165)
    # STALE guard: the defect was the box staying at the 1.0 px on a 1.5 card.
    assert scaled["cover"][2] != _COVER[2]


def test_text_row_zone_scales_once(qapp) -> None:
    base, scaled = _snapshot(1.0), _snapshot(1.5)
    assert base["text"] == (0, _TEXT_TOP, GALLERY_CARD_W, _TEXT_H)
    assert scaled["text"] == (
        0,
        int(scaled_px(_TEXT_TOP)),
        int(scaled_px(GALLERY_CARD_W)),
        int(scaled_px(_TEXT_H)),
    )
    assert scaled["text"] == (0, 177, 375, 78)


def test_metric_dots_pitch_and_painted_diameter_scale_once(qapp) -> None:
    """Dots are painted chrome — pitch AND diameter must follow the factor."""
    base, scaled = _snapshot(1.0), _snapshot(1.5)
    assert base["dot_pitch"] == pytest.approx(float(DOT_PITCH))
    assert base["dot_step"] == pytest.approx(float(DOT_PITCH))
    assert int(scaled_px(DOT_PITCH)) == 21
    assert scaled["dot_pitch"] == pytest.approx(21.0)
    assert scaled["dot_step"] == pytest.approx(21.0)

    # Painted diameter (not just the stashed pitch): 8 design px -> 12 at 1.5.
    widget10 = _fake_widget([QColor(200, 0, 0)])
    image10, _h = _paint_overlay(1.0, widget10)
    run10 = _ink_run(image10, *widget10._gallery_dot_geometry["centers"][0])
    widget15 = _fake_widget([QColor(200, 0, 0)])
    image15, _h = _paint_overlay(1.5, widget15)
    run15 = _ink_run(image15, *widget15._gallery_dot_geometry["centers"][0])
    assert run10 == pytest.approx(float(DOT_DIAMETER), abs=1)
    assert run15 == pytest.approx(float(int(scaled_px(DOT_DIAMETER))), abs=1)
    assert run15 > run10


def test_rank_badge_pill_scales_once(qapp) -> None:
    """The painted #N pill is card chrome: position and height follow the factor."""

    def span_and_top(factor: float) -> tuple[int, int]:
        from tabs.image_gallery.services.rank_badge import BADGE_RADIUS

        widget = _fake_widget([])
        widget._gallery_badge = "3"
        widget._gallery_badge_style = (
            True,
            QColor(0, 120, 200),
            QColor(0, 120, 200),
            _WHITE,
        )
        image, h = _paint_overlay(factor, widget)
        # Sample a column at the pill's left-edge tangent (dx == radius) so the
        # rounded corner does not clip the measured height.
        x = int(round(float(scaled_px(13)) + float(scaled_px(BADGE_RADIUS))))
        ys = [y for y in range(h) if image.pixelColor(x, y) != _WHITE]
        assert ys, "badge pill painted nothing"
        return (max(ys) - min(ys) + 1), min(ys)

    height10, top10 = span_and_top(1.0)
    height15, top15 = span_and_top(1.5)
    # Design pill: 18 tall at top 8+6 = 14 (the 1px pen adds ~1px of ink).
    assert height10 == pytest.approx(18, abs=2)
    assert top10 == pytest.approx(14, abs=1)
    # At 1.5 the pill must grow to ~27 (NOT stay 18) and drop to ~21 (NOT 14).
    assert height15 == pytest.approx(int(scaled_px(18)), abs=2)
    assert top15 == pytest.approx(int(scaled_px(8)) + int(scaled_px(6)), abs=1)
    assert height15 - height10 >= int(scaled_px(18)) - 18 - 1


def test_card_rederives_boxes_on_a_live_scale_change(qapp) -> None:
    """A live UiScale flip re-derives the card in place (no rebuild, no restart).

    Falsification: the reported bug (red before ``4d5a7572``) was the live
    card keeping its build-time cover/text boxes after ``set_factor(1.5)`` —
    the cover read ``(8, 8, 234, 110)`` where the scaled card needs
    ``(12, 12, 351, 165)``. The re-derivation rides the coalesced metrics
    channel (a zero-timer), so the read is drained first. The evidence record
    is derived from the observed rects: a stale cache emits ``violated`` with
    the measured numbers and fails this probe.
    """
    card = _card(1.0)
    try:
        card.render(QPixmap(card.size()))
        assert _rect_ints(card.region_rect("cover")) == _COVER

        UiScale.get_instance().set_factor(1.5)
        drain_until_stable(qapp, lambda: _rect_ints(card.region_rect("cover")))
        card.render(QPixmap(card.size()))

        assert (card.width(), card.height()) == (375, 255)
        assert _rect_ints(card.region_rect("cover")) == (12, 12, 351, 165)
        assert int(card.region_rect("text").top()) == 177

        observed_cover = _rect_ints(card.region_rect("cover"))
        expected_cover = tuple(int(scaled_px(v)) for v in _COVER)
        record_evidence("spec.ui.scale_parity",
                        kind="spec",
                        verdict="ok" if observed_cover == expected_cover else "violated",
                        signal=(f"factor={UiScale.get_instance().factor()} "
                                f"cover={observed_cover} expected={expected_cover} "
                                f"card={card.width()}x{card.height()}"),
                        reason="owned derived geometry re-derived after a live scale change",
                        ids=("card:build_gallery_card",),
                        area="image_gallery.card")
        record = verdict(None, "spec.ui.scale_parity")
        assert record is not None, "scale-parity probe emitted no evidence"
        assert record.verdict == "ok", record.signal
    finally:
        card.deleteLater()
