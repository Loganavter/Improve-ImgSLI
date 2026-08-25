"""Recent-color store + chip row for the color picker."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from tests.helpers.drain_until_stable import drain_until_stable
from ui.widgets.color import (
    RECENT_COLORS_CAP,
    RecentColorsRow,
    RecentColorsStore,
    color_to_hex_string,
    parse_hex_color,
)


@pytest.fixture
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def settings(tmp_path):
    return QSettings(os.path.join(str(tmp_path), "cfg.ini"), QSettings.Format.IniFormat)


def test_parse_hex_color_six_and_eight_digit():
    color = parse_hex_color("#ff8800")
    assert (color.red(), color.green(), color.blue(), color.alpha()) == (255, 136, 0, 255)
    color = parse_hex_color("ff8800")
    assert (color.red(), color.green(), color.blue()) == (255, 136, 0)
    color = parse_hex_color("#FF8800AA")
    assert (color.red(), color.green(), color.blue(), color.alpha()) == (255, 136, 0, 170)


def test_parse_hex_color_rejects_bad_input():
    for bad in ("", "#12345", "#1234567", "#gggggg", "ff8800aa11", None):
        assert parse_hex_color(bad) is None, bad


def test_color_to_hex_string():
    assert color_to_hex_string(QColor(255, 136, 0, 255)) == "#FF8800"
    assert color_to_hex_string(QColor(255, 136, 0, 255), include_alpha=True) == "#FF8800"
    assert color_to_hex_string(QColor(255, 136, 0, 170), include_alpha=True) == "#FF8800AA"


def test_store_roundtrip_and_dedupe(settings):
    store = RecentColorsStore(settings)
    assert store.load() == []
    store.add("#FF8800AA")
    store.add("ff8800")
    store.add("#FF8800")  # case-insensitive dedupe
    assert store.load() == ["#FF8800", "#FF8800AA"]


def test_store_persists_across_instances(settings):
    RecentColorsStore(settings).add("#112233")
    RecentColorsStore(settings).add("#445566")
    assert RecentColorsStore(settings).load() == ["#445566", "#112233"]


def test_store_caps_and_filters_invalid(settings):
    store = RecentColorsStore(settings)
    for i in range(15):
        store.add(f"#{i:02X}0000")
    colors = store.load()
    assert len(colors) == RECENT_COLORS_CAP
    assert colors[0] == "#0E0000"  # most recent first
    settings.setValue(
        "color_picker/recents",
        ["#FF0000", "garbage", "#00FF00"],
    )
    assert RecentColorsStore(settings).load() == ["#FF0000", "#00FF00"]


def test_store_ignores_invalid_add(settings):
    store = RecentColorsStore(settings)
    store.add("not-a-color")
    assert store.load() == []


def test_row_hidden_when_empty(qapp):
    row = RecentColorsRow()
    try:
        row.set_colors([])
        assert row.isHidden()
    finally:
        row.deleteLater()


def test_row_shows_chips_and_emits_picked(qapp):
    row = RecentColorsRow(caption="Recent")
    picked = []
    row.recentPicked.connect(picked.append)
    try:
        row.set_colors(["#FF8800AA"])
        assert not row.isHidden()
        assert row._caption.text() == "Recent"
        assert len(row._chip_widgets) == 1  # single chip in the grid
        chip = row._chip_widgets[0]
        QTest.mouseClick(chip, Qt.MouseButton.LeftButton)
        assert len(picked) == 1
        color = picked[0]
        assert (color.red(), color.green(), color.blue(), color.alpha()) == (255, 136, 0, 170)
    finally:
        row.deleteLater()


def test_chip_hover_ring_and_no_resting_border(qapp):
    from PySide6.QtCore import QEvent, QPointF
    from PySide6.QtGui import QEnterEvent

    row = RecentColorsRow(caption="Recent")
    try:
        row.set_colors(["#FF8800"])
        row.show()
        drain_until_stable(
            qapp,
            lambda: (row._chip_widgets[0].width(), row._chip_widgets[0].height()) if row._chip_widgets else (0, 0),
            timeout_ms=800,
            poll_ms=10,
            stable_frames=2,
        )
        chip = row._chip_widgets[0]
        assert not chip._hovered
        assert chip.width() >= 60  # ~3x the old 22px chip
        # Offscreen has no window-system enter synthesis — deliver events
        # directly (same handlers QTest/Qt would route through).
        center = QPointF(chip.rect().center())
        enter = QEnterEvent(center, center, QPointF(0, 0))
        QApplication.sendEvent(chip, enter)
        assert chip._hovered
        QApplication.sendEvent(chip, QEvent(QEvent.Type.Leave))
        assert not chip._hovered
    finally:
        row.deleteLater()


def test_row_wraps_chips_onto_rows_when_narrow(qapp):
    from PySide6.QtWidgets import QVBoxLayout, QWidget

    # Dialog minimum width (260px) — the narrowest a real shelf can be.
    host = QWidget()
    host.setFixedSize(260, 500)
    lay = QVBoxLayout(host)
    row = RecentColorsRow(caption="Recent")
    lay.addWidget(row)
    try:
        row.set_colors([f"#{i:02X}0000" for i in range(6)])
        host.show()
        drain_until_stable(
            qapp,
            lambda: tuple((c.x(), c.y(), c.width()) for c in row._chip_widgets),
            timeout_ms=800,
            poll_ms=10,
            stable_frames=2,
        )
        rows = {chip.y() for chip in row._chip_widgets}
        # 260px fits three 64px chips per row -> 6 chips on 2 rows.
        assert len(rows) >= 2
        # At most three distinct chip x positions (three columns).
        assert len({chip.x() for chip in row._chip_widgets}) <= 3
    finally:
        row.deleteLater()
        host.deleteLater()


def test_row_positions_stable_across_resizes(qapp):
    row = RecentColorsRow()
    try:
        row.set_colors(["#FF0000", "#00FF00"])
        row.resize(400, 400)
        row.show()
        drain_until_stable(
            qapp,
            lambda: tuple((c.x(), c.width()) for c in row._chip_widgets),
            timeout_ms=800,
            poll_ms=10,
            stable_frames=2,
        )
        chips = [row._chip_widgets[i] for i in range(2)]
        positions = [(c.x(), c.width()) for c in chips]
        for width in (400, 500, 400):
            row.resize(width, row.height())
            drain_until_stable(
                qapp,
                lambda: tuple((c.x(), c.width()) for c in row._chip_widgets),
                timeout_ms=800,
                poll_ms=10,
                stable_frames=2,
            )
            positions_now = [(c.x(), c.width()) for c in chips]
            assert positions_now == positions
    finally:
        row.deleteLater()