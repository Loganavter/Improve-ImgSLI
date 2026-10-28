"""Find Action materializes only the visible slice of its results.

Owner report 2026-10-28 (after the row-reuse fix): «не, ну долго почему-то.
Может подлагивать. У нас виртуализации списка нету что ли?» — correct: the dialog
built one composite row widget (~2.7 ms each) for **every** action up front, so
opening it on a 100-action catalog cost 375 ms before a single pixel was shown.

The list is now virtualized: rows exist only for the visible window plus a small
overscan, the two spacers carry the rest of the scroll extent, and scrolling or
moving the selection materializes the rows it needs.

Red-before: on the previous tree the dialog materialized every action, so
`len(dialog._rows_by_id)` equalled the catalog size and the top spacer stayed 0.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication

from core.actions.types import ActionDescriptor
from ui.actions.palette.dialog import FindActionDialog
from ui.actions.registry import get_action_registry, reset_action_registry_for_tests

CATALOG_SIZE = 300


@pytest.fixture
def catalog():
    reset_action_registry_for_tests()
    registry = get_action_registry()
    for i in range(CATALOG_SIZE):
        registry.register(
            ActionDescriptor(
                action_id=f"probe.virtual.{i:03d}",
                label_key=f"probe.virtual.label.{i:03d}",
                run=lambda: None,
            )
        )
    yield registry
    reset_action_registry_for_tests()


def _open(qtbot) -> FindActionDialog:
    dialog = FindActionDialog(None, query="")
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitExposed(dialog)
    qtbot.wait(150)
    return dialog


def test_only_the_visible_slice_is_materialized(qtbot, catalog):
    dialog = _open(qtbot)
    try:
        assert len(dialog._actions) == CATALOG_SIZE
        materialized = len(dialog._rows)
        assert 0 < materialized <= 40, (
            f"{materialized} rows exists for a {CATALOG_SIZE}-action catalog; "
            "only the visible window (+overscan) may be built"
        )
        assert dialog._rows[0].action_id == "probe.virtual.000"
        assert dialog._bottom_spacer.height() > 0, (
            "the spacer must carry the scroll extent of the unmaterialized rest"
        )
        assert dialog._top_spacer.height() == 0
    finally:
        dialog.close()
        dialog.deleteLater()


def test_scrolling_materializes_the_window_under_the_viewport(qtbot, catalog):
    dialog = _open(qtbot)
    try:
        pitch = dialog._row_pitch()
        bar = dialog._scroll.verticalScrollBar()
        target = 150 * pitch
        bar.setValue(min(target, bar.maximum()))
        QApplication.processEvents()

        assert dialog._top_spacer.height() > 0
        materialized = {row.action_id for row in dialog._rows}
        first = dialog._window_start
        assert f"probe.virtual.{first:03d}" in materialized
        assert len(dialog._rows) <= 40
        assert f"probe.virtual.{first + len(dialog._rows) - 1:03d}" in materialized
    finally:
        dialog.close()
        dialog.deleteLater()


def test_moving_the_selection_materializes_its_row(qtbot, catalog):
    dialog = _open(qtbot)
    try:
        dialog._set_current_index(200)
        QApplication.processEvents()
        current = [row for row in dialog._rows if row.is_current]
        assert current and current[0].action_id == "probe.virtual.200", (
            "arrow-key selection must materialize the row it lands on"
        )
        assert dialog._actions[dialog._current_index].action_id == "probe.virtual.200"
    finally:
        dialog.close()
        dialog.deleteLater()


def test_first_rows_are_visible_inside_the_viewport(qtbot, catalog):
    """The windowed list must actually show its rows (owner screenshot: blank)."""
    dialog = _open(qtbot)
    try:
        assert dialog._rows, "no rows materialized"
        viewport = dialog._scroll.viewport()
        first = dialog._rows[0]
        assert first.isVisible(), "the first row is hidden"
        offset = first.mapTo(viewport, QPoint(0, 0)).y()
        assert 0 <= offset < viewport.height(), (
            f"the first row sits at y={offset} in a {viewport.height()}px "
            "viewport - the spacers must stay outside the row band"
        )
        second = dialog._rows[1]
        assert second.mapTo(viewport, QPoint(0, 0)).y() > offset
    finally:
        dialog.close()
        dialog.deleteLater()
