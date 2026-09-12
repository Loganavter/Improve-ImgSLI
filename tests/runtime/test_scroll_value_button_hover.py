"""ScrollValueButton hover must cover the full grouped capsule after split."""

from __future__ import annotations

from PySide6.QtCore import QPoint
from PySide6.QtGui import QEnterEvent

from ui.widgets.scroll_value_button import ScrollValueButton


def _enter(button: ScrollValueButton, pos: QPoint) -> None:
    local = QPoint(pos).toPointF()
    event = QEnterEvent(local, local, button.mapToGlobal(pos))
    button.enterEvent(event)


def test_hover_split_covers_both_grouped_regions(qtbot):
    button = ScrollValueButton(icon=None, min_value=0, max_value=10, start=4)
    qtbot.addWidget(button)
    button.show()
    qtbot.waitExposed(button)

    _enter(button, button.rect().center())

    assert button._hovered_split is True
    assert {r.id for r in button.regions()} == {"icon", "value"}
    assert button.region("icon").hovered
    assert button.region("value").hovered


def test_hover_split_toggle_button_covers_main_and_value(qtbot):
    button = ScrollValueButton(
        icon=None,
        toggle=True,
        min_value=0,
        max_value=10,
        start=3,
    )
    qtbot.addWidget(button)
    button.show()
    qtbot.waitExposed(button)

    _enter(button, button.rect().center())

    assert {r.id for r in button.regions()} == {"_main", "value"}
    assert button.region("_main").hovered
    assert button.region("value").hovered


def test_value_change_while_hovered_keeps_group_wash(qtbot):
    button = ScrollValueButton(icon=None, min_value=0, max_value=10, start=2)
    qtbot.addWidget(button)
    button.show()
    qtbot.waitExposed(button)

    _enter(button, button.rect().center())
    button.set_value(5)

    assert button.region("icon").hovered
    assert button.region("value").hovered
