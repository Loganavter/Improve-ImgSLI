"""Find Action must filter on the keystroke and land at the top of the list.

Owner report 2026-10-28: «дебаунс слишком большой» and «при написании или стирании
символов мы не оказываемся в самом верху списка». The reference the owner named is
GIMP's action search (``app/widgets/gimpsearchpopup.c``,
``keyword_entry_key_release_event``): it rebuilds the results on **every** key
release, then selects row 0 — no debounce, and the selection returns the list to
the top.

Red-before: the dialog used a 90 ms debounce (a single event-loop turn did not
apply the query) and re-selected row 0 with "ensure visible", which leaves a list
that is already scrolled down exactly where it was.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from core.actions.types import ActionDescriptor
from ui.actions.palette import dialog as palette_dialog
from ui.actions.palette.dialog import FindActionDialog
from ui.actions.registry import get_action_registry, reset_action_registry_for_tests


@pytest.fixture
def catalog():
    reset_action_registry_for_tests()
    registry = get_action_registry()
    for i in range(40):
        registry.register(
            ActionDescriptor(
                action_id=f"probe.live.{i:02d}",
                label_key=f"probe.live.label.{i:02d}",
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


def test_query_is_applied_on_the_same_event_loop_turn(qtbot, catalog):
    dialog = _open(qtbot)
    try:
        dialog._search.setText("label.03")
        QApplication.processEvents()  # one turn - a debounce would not fire here
        assert [a.action_id for a in dialog._actions] == ["probe.live.03"], (
            "the query must be applied on the keystroke, not after a delay "
            "(GIMP filters on key release)"
        )
    finally:
        dialog.close()
        dialog.deleteLater()


def test_a_query_change_returns_the_list_to_the_top(qtbot, catalog):
    dialog = _open(qtbot)
    try:
        bar = dialog._scroll.verticalScrollBar()
        assert bar.maximum() > 0, "the catalog must overflow for this case"
        bar.setValue(bar.maximum())
        QApplication.processEvents()
        assert bar.value() > 0

        dialog._search.setText("label.1")
        QApplication.processEvents()
        assert dialog._rows, "the query must still match something"
        assert bar.value() == bar.minimum(), (
            "a new query must show its best match at the top of the list "
            "(GIMP selects row 0 after every rebuild)"
        )

        # Erasing back to the full list must also land at the top.
        bar.setValue(bar.maximum())
        QApplication.processEvents()
        dialog._search.setText("")
        QApplication.processEvents()
        assert bar.value() == bar.minimum()
    finally:
        dialog.close()
        dialog.deleteLater()


def test_reload_is_not_delayed(qtbot, catalog):
    """A timer above zero re-introduces the sticky search box."""
    assert palette_dialog._RELOAD_DEBOUNCE_MS == 0, (
        "the reload must not be delayed by a timer - rows are reused and cheap"
    )
