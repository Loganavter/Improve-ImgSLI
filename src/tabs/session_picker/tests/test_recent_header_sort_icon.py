"""The Recent-shelf sort chip must show an icon for the current sort mode.

Falsification (pre-fix): ``RecentHeaderBar`` built ``sort_button`` with text only
(no ``icon=``), so the chip rendered without the leading icon while the dropdown
rows carried one (SORT_BY_MODIFIED / _CREATED / _NAME).

Icons are lazy handles (``lazy_icon``) resolved at paint time against the live
mode + theme; assert via ``resolve_icon``.
"""

from __future__ import annotations

from PySide6.QtGui import QColor
from sli_ui_toolkit.icons import resolve_icon

from tabs.session_picker.icons import Icon as SessionPickerIcon
from tabs.session_picker.recent.header_bar import (
    SORT_CREATED,
    SORT_NAME,
    RecentHeaderBar,
)


def _bar(qtbot) -> RecentHeaderBar:
    bar = RecentHeaderBar(translate=lambda k, d: d)
    qtbot.addWidget(bar)
    return bar


def test_sort_button_has_an_icon(qtbot) -> None:
    bar = _bar(qtbot)
    assert not resolve_icon(
        bar.sort_button._icon_unchecked
    ).isNull(), "sort chip has no icon"


def test_sort_button_icon_follows_the_mode(qtbot) -> None:
    bar = _bar(qtbot)
    bar.sync(
        has_items=True, sort_mode=SORT_NAME, sort_order="desc",
        view_mode="grid", chip_bg=QColor("#ffffff"),
    )
    assert bar._sort_mode_icon() == SessionPickerIcon.SORT_BY_NAME
    assert not resolve_icon(bar.sort_button._icon_unchecked).isNull()

    bar.sync(
        has_items=True, sort_mode=SORT_CREATED, sort_order="desc",
        view_mode="grid", chip_bg=QColor("#ffffff"),
    )
    assert bar._sort_mode_icon() == SessionPickerIcon.SORT_BY_CREATED
