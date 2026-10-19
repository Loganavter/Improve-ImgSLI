"""Keyboard model of the colour picker's recents shelf: a real 2D grid.

Falsification story (owner report 2026-10-19, screenshot): the shelf wraps its
chips onto 2+ visual rows, but the picker declared the whole shelf as ONE
``ToolbarRowsSection`` row. On that model — and on any implementation that only
adds a section without a real row model — ``Down`` on the first chip leaves the
whole block (the chips are one "row" to it, so the row edge declines instead of
entering the row below), and ``Right`` on the last chip of a visual row steps
into the *next visual row* (the inherited x-sort). The grid tests below encode
the opposite: ``Down`` lands on the chip directly below, ``Right`` at a visual
row end declines (``False``, no wrap), ``Up`` lands on the nearest-x chip of the
row above, and both vertical edges decline. They are red on the single-row
model — a one-row section over the same chips declines the Down assertions and
moves cross-row on the Right assertion.

The wiring test drives the REAL ``NavigationManager`` over a stub dialog whose
rows mirror the picker's (fields / recents / actions), so the block's vertical
exits are exercised through the same composition
``register_recents_grid`` installs in ``ColorPickerDialog``.

Hermetic: stdlib QSettings, offscreen widgets, no app boot, no MCP.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QHBoxLayout, QPushButton, QVBoxLayout, QWidget

from sli_ui_toolkit.managers import NavigationManager, UiScale, declare_navigation_rows
from ui.widgets.color.recents import RecentColorsRow, _RecentColorChip
from ui.widgets.color.recents_nav import (
    RecentsGridNavSection,
    register_recents_grid,
    unregister_recents_grid,
)

# 12 chips at 340 px wrap to 3 visual rows of 4 (chip 64 px + 10 px spacing at
# scale 1.0: columns = (340 - 16 + 10) // 74 = 4). A resize to 590 px gives
# 7 columns -> rows of 7 + 5, a real wrap change.
_COLORS = [f"#{i + 1:02X}{i:02X}00" for i in range(12)]


@pytest.fixture
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def _factor_one():
    """UiScale is a process-wide singleton; leave the factor at 1.0."""
    UiScale.get_instance().set_factor(1.0)
    yield
    UiScale.get_instance().set_factor(1.0)


def _focus(widget: QWidget) -> None:
    widget.setFocus(Qt.FocusReason.OtherFocusReason)
    QApplication.instance().processEvents()
    assert QApplication.focusWidget() is widget, (
        f"{type(widget).__name__} did not receive focus (offscreen window not active?)"
    )


def _row(width: int = 340) -> RecentColorsRow:
    """Shelf with 12 chips wrapped at *width*; shown for real focus delivery."""
    row = RecentColorsRow(caption="Recent")
    row.resize(width, 400)
    row.set_colors(_COLORS)
    row.show()
    QTest.qWaitForWindowExposed(row)
    QApplication.instance().processEvents()
    return row


def _grid(row: RecentColorsRow) -> tuple[RecentsGridNavSection, list]:
    return RecentsGridNavSection(row), row.live_chips()


def test_setup_wraps_chips_into_three_visual_rows(qapp):
    """Guard for every test below: the fixture really produces 2+ visual rows."""
    row = _row()
    try:
        assert [len(r) for r in row.chip_rows()] == [4, 4, 4]
    finally:
        row.close()
        row.deleteLater()


def test_down_moves_to_the_first_chip_of_the_next_visual_row(qapp):
    row = _row()
    try:
        grid, chips = _grid(row)
        _focus(chips[0])

        assert grid.navigate(Qt.Key.Key_Down, chips[0]) is True

        assert QApplication.focusWidget() is chips[4], (
            "Down must land on the chip directly below (same column), not leave "
            "the single-row block nor step one chip right"
        )
    finally:
        row.close()
        row.deleteLater()


def test_right_at_visual_row_end_declines_without_wrapping(qapp):
    row = _row()
    try:
        grid, chips = _grid(row)
        last_of_first_row = row.chip_rows()[0][-1]
        _focus(last_of_first_row)

        assert grid.navigate(Qt.Key.Key_Right, last_of_first_row) is False, (
            "a visual-row edge must decline — no wrap and no hop into the next "
            "visual row (chip order 3 -> 4 in x order)"
        )
        assert QApplication.focusWidget() is last_of_first_row

        first_of_row = row.chip_rows()[1][0]
        _focus(first_of_row)
        assert grid.navigate(Qt.Key.Key_Left, first_of_row) is False
        assert QApplication.focusWidget() is first_of_row
    finally:
        row.close()
        row.deleteLater()


def test_up_lands_on_the_nearest_x_chip_of_the_previous_row(qapp):
    row = _row()
    try:
        grid, chips = _grid(row)
        # Chip 5 is the second column of the middle row -> chip 1 above it.
        _focus(chips[5])

        assert grid.navigate(Qt.Key.Key_Up, chips[5]) is True
        assert QApplication.focusWidget() is chips[1], (
            "Up must follow the 2D rule: nearest x-center in the row above"
        )
    finally:
        row.close()
        row.deleteLater()


def test_up_from_top_row_and_down_from_bottom_row_decline(qapp):
    row = _row()
    try:
        grid, chips = _grid(row)
        _focus(chips[0])
        assert grid.navigate(Qt.Key.Key_Up, chips[0]) is False
        assert QApplication.focusWidget() is chips[0]

        bottom = row.chip_rows()[-1]
        _focus(bottom[0])
        assert grid.navigate(Qt.Key.Key_Down, bottom[0]) is False
        assert QApplication.focusWidget() is bottom[0]
    finally:
        row.close()
        row.deleteLater()


def test_arrows_follow_the_new_wrap_after_a_resize(qapp):
    row = _row()
    try:
        grid, chips = _grid(row)
        assert [len(r) for r in row.chip_rows()] == [4, 4, 4]

        row.resize(590, 400)
        QApplication.instance().processEvents()
        assert [len(r) for r in row.chip_rows()] == [7, 5], (
            "the resize must re-wrap the chips (the test needs a NEW column "
            "count for the stale-model check to mean anything)"
        )

        # 7 columns: chip 6 is the last chip of the first visual row, and its
        # x-center (484) is nearest chip 11 (336) in the new 5-chip second row.
        _focus(chips[6])
        assert grid.navigate(Qt.Key.Key_Down, chips[6]) is True
        assert QApplication.focusWidget() is chips[11], (
            "Down must follow the NEW rows, not a cached 4-column model"
        )

        # …and back up from chip 11: x-center 336, nearest chip in the 7-chip
        # first row is chip 4 (the short second row makes this asymmetric —
        # nearest-x, not "same index").
        assert grid.navigate(Qt.Key.Key_Up, chips[11]) is True
        assert QApplication.focusWidget() is chips[4]
    finally:
        row.close()
        row.deleteLater()


def test_enter_and_space_on_a_focused_chip_still_activate(qapp):
    row = _row()
    try:
        picked: list[QColor] = []
        row.recentPicked.connect(picked.append)
        chip = row.live_chips()[0]
        _focus(chip)

        QTest.keyClick(chip, Qt.Key.Key_Return)
        QTest.keyClick(chip, Qt.Key.Key_Space)

        assert picked == [QColor(chip._color), QColor(chip._color)], (
            "Enter/Space must keep activating the focused chip (recentPicked)"
        )
    finally:
        row.close()
        row.deleteLater()


def test_owns_only_live_chips(qapp):
    row = _row()
    try:
        grid, chips = _grid(row)
        parent = QWidget()
        try:
            parent.show()
            QApplication.instance().processEvents()
            assert grid.owns(row) is False, "the shelf host is not a grid item"
            assert grid.owns(row.content_host()) is False
            assert grid.owns(parent) is False
            assert all(grid.owns(chip) for chip in chips)

            stale = chips[0]
            row.set_colors(_COLORS[:3])
            QApplication.instance().processEvents()
            assert grid.owns(stale) is False, (
                "chips replaced by set_colors must not stay owned (stale focus "
                "targets are what send arrows to a deleted widget)"
            )
            assert all(grid.owns(chip) for chip in row.live_chips())
        finally:
            parent.deleteLater()
    finally:
        row.close()
        row.deleteLater()


def test_focus_ring_gutter_is_reserved_and_scales(qapp):
    chip = _RecentColorChip("#FF8800")
    try:
        gutter = (chip.width() - chip.content_rect().width()) / 2
        assert gutter >= 2, (
            "the FocusLayer ring is drawn inside the content rect; without a "
            f"≥2 px gutter it sits flush on the chip edge (got {gutter})"
        )

        pixmap = QPixmap(chip.size())
        painter = QPainter(pixmap)
        try:
            assert chip._focus_ctx(painter).rect == chip.content_rect(), (
                "the focus ring must be painted on the guttered content rect"
            )
        finally:
            painter.end()
        pixmap = None

        UiScale.get_instance().set_factor(2.0)
        chip.apply_metrics()
        scaled_gutter = (chip.width() - chip.content_rect().width()) / 2
        assert scaled_gutter == 2 * gutter, (
            f"the gutter must scale with UiScale: {gutter} -> {scaled_gutter}"
        )
    finally:
        UiScale.get_instance().set_factor(1.0)
        chip.deleteLater()


def test_wired_picker_rows_leave_the_block_vertically(qapp):
    """End-to-end through ``NavigationManager`` (the real picker composition).

    A single-row model answers both presses below itself (Down moves within
    the block, Right hops rows); the wired grid must instead leave Down from
    the bottom row to the action buttons, Up from the top row to the fields,
    and keep Right at a visual row end on the same chip.
    """
    host = QWidget()
    host.setWindowFlags(Qt.WindowType.Dialog)
    host.resize(400, 420)
    root = QVBoxLayout(host)
    root.setContentsMargins(16, 14, 16, 14)
    root.setSpacing(12)

    fields = QWidget(host)
    fields_row = QHBoxLayout(fields)
    fields_row.setContentsMargins(0, 0, 0, 0)
    field_button = QPushButton("FIELD", fields)
    fields_row.addWidget(field_button)
    root.addWidget(fields)

    recents = RecentColorsRow(host)
    recents.set_colors(_COLORS)
    root.addWidget(recents)

    actions = QWidget(host)
    actions_row = QHBoxLayout(actions)
    actions_row.setContentsMargins(0, 0, 0, 0)
    action_button = QPushButton("OK", actions)
    actions_row.addWidget(action_button)
    root.addWidget(actions)

    host.show()
    try:
        QTest.qWaitForWindowExposed(host)
        QApplication.instance().processEvents()
        declare_navigation_rows(host, [fields, recents, actions], tag="stub-picker")
        register_recents_grid(host, recents)
        QApplication.instance().processEvents()

        chips = recents.live_chips()
        assert [len(r) for r in recents.chip_rows()] == [4, 4, 4]

        # Right at the visual row edge stays put (the declared row's linear
        # x-walk must not run for the grid).
        _focus(chips[3])
        QTest.keyClick(chips[3], Qt.Key.Key_Right)
        QApplication.instance().processEvents()
        assert QApplication.focusWidget() is chips[3]

        # Down from the bottom row leaves to the action row.
        _focus(chips[11])
        QTest.keyClick(chips[11], Qt.Key.Key_Down)
        QApplication.instance().processEvents()
        assert QApplication.focusWidget() is action_button

        # Up from the action row returns into the block, then Up from the top
        # row leaves to the fields row.
        QTest.keyClick(action_button, Qt.Key.Key_Up)
        QApplication.instance().processEvents()
        assert QApplication.focusWidget() in chips

        _focus(chips[0])
        QTest.keyClick(chips[0], Qt.Key.Key_Up)
        QApplication.instance().processEvents()
        assert QApplication.focusWidget() is field_button
    finally:
        unregister_recents_grid(host)
        NavigationManager.get_instance().unregister(host)
        host.close()
        host.deleteLater()
