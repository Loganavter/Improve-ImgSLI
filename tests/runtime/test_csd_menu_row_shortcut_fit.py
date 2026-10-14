"""CSD dropdown rows must never clip the right-aligned shortcut.

Regression: ``CsdMenuRow`` splits each row into a leading label region and a
fixed-width shortcut region of ``measure_text_width(fm, shortcut) + gap`` px.
But the toolkit's row painter subtracts the widget-wide ``content_padding``
from *every* region rect (``content._rect``), not only from the leading
icon+label one. The shortcut region therefore lost ``content_left +
content_right`` px of usable width. With the app's icon+label padding
(left 32, right 8) a long chord such as ``Ctrl+Shift+O`` was painted into a
49px slot instead of 69px and the leading glyphs were clipped
(``Ctrl+Shift+O`` → ``hift+O``; the reported ``Ctrl+S`` → ``t+S``).

The geometry test measures the *effective* slot (region width minus the
padding the painter actually applies) against the row's real render font.
The pixel test diffs a rendered row against the same row without a shortcut,
so it proves the painted glyphs are not left-clipped — independent of the
slot arithmetic.
"""

from __future__ import annotations

import pytest
from PySide6.QtGui import QFontMetrics, QImage

from sli_ui_toolkit.managers import UiScale, ui_font
from sli_ui_toolkit.widgets import ContextMenuAction

from ui.main_window.csd_menu_strip import CsdMenuRow, _SHORTCUT_PIXEL_SIZE

# Worst case: a long modifier chord on a long label. Every CSD row carries an
# icon, which is what makes the left content padding (8 + icon lead) eat into
# the shortcut slot — without the icon the defect is only 4px.
_LABEL = "Open Project"
_SHORTCUT = "Ctrl+Shift+O"
_FACTORS = (1.0, 1.25, 1.5, 2.0)


@pytest.fixture(autouse=True)
def _restore_ui_scale():
    """Parametrized scale tests must not leak the process-wide factor."""
    yield
    UiScale.get_instance().set_factor(1.0)


def _icon():
    from ui.icon_manager import get_app_icon

    return get_app_icon("folder_open.svg")


def _build_row(shortcut: str = _SHORTCUT, *, width: int | None = None) -> CsdMenuRow:
    action = ContextMenuAction(
        action_id="test.row",
        text=_LABEL,
        shortcut=shortcut,
        icon=_icon(),
    )
    row = CsdMenuRow(action)
    hint = row.sizeHint()
    row.resize(width or hint.width(), hint.height())
    row._recompute_region_rects()
    return row


def _rendered_shortcut_width(shortcut: str = _SHORTCUT) -> int:
    """Advance of the shortcut in the exact font the row paints it with."""
    fm = QFontMetrics(ui_font(pixel_size=_SHORTCUT_PIXEL_SIZE))
    return fm.horizontalAdvance(shortcut)


def _effective_slot_width(row: CsdMenuRow) -> float:
    """Shortcut slot width *after* the painter subtracts content padding.

    ``Button`` applies the widget-wide ``content_padding`` to each region
    rect, so the width a region paints into is ``region.width() - left -
    right``. This is the number that must cover the painted glyphs.
    """
    rect = row.region_rect("shortcut")
    left, _top, right, _bottom = row._content_padding
    return rect.width() - left - right


@pytest.mark.parametrize("factor", _FACTORS)
def test_shortcut_slot_covers_rendered_width(qapp, factor):
    """The usable shortcut region must fit the glyphs it paints, at any scale."""
    UiScale.get_instance().set_factor(factor)
    row = _build_row()
    rendered = _rendered_shortcut_width()
    effective = _effective_slot_width(row)
    assert effective >= rendered, (
        f"factor {factor}: shortcut slot {effective:.0f}px < rendered "
        f"{rendered}px ({rendered - effective:.0f}px left-clipped)"
    )


def test_shortcut_glyphs_painted_without_left_clip(qapp):
    """Pixel proof: the painted shortcut is not cut off on the left.

    Rendering the same row with and without a shortcut isolates the shortcut
    glyphs (the label and background are byte-identical between the two
    renders); the leftmost differing column is where the shortcut ink starts.
    Pre-fix it started ``content_left`` px too far right — the clip.
    """
    row = _build_row()
    rect = row.region_rect("shortcut")
    right_pad = row._content_padding[2]
    rendered = _rendered_shortcut_width()
    expected_left = rect.right() - right_pad - rendered

    with_shortcut = _render(row)
    without_shortcut = _render(_build_row(shortcut="", width=with_shortcut.width()))
    painted = [
        x
        for x in range(with_shortcut.width())
        if _column_differs(with_shortcut, without_shortcut, x)
    ]
    assert painted, "no shortcut glyphs were painted at all"
    painted_left = min(painted)
    assert painted_left <= expected_left + 2, (
        f"shortcut ink starts at x={painted_left}, expected <= "
        f"{expected_left + 2:.0f} — leading glyphs are left-clipped"
    )


def _render(row: CsdMenuRow) -> QImage:
    image = QImage(row.width(), row.height(), QImage.Format.Format_ARGB32)
    image.fill(0)
    row.render(image)
    return image


def _column_differs(a: QImage, b: QImage, x: int) -> bool:
    return any(
        a.pixelColor(x, y) != b.pixelColor(x, y) for y in range(a.height())
    )
