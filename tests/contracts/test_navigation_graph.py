"""Navigation graph contract — POC for navigation-robustness-plan.

Covers the two recent focus-ring/tab-strip fixes so they can't regress
without a test failure, instead of requiring log.txt triage.

Dogma source: docs/dev/investigations/navigation-robustness-plan.md,
sli_ui_toolkit/.../nav_graph.py, FILE_SIZE_POLICY.md precedent.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication


def test_focus_reason_respects_modality(qapp):
    from sli_ui_toolkit.ui.managers.navigation_manager import NavigationManager
    from sli_ui_toolkit.ui.managers.nav_graph import focus_reason

    mgr = NavigationManager.get_instance()
    # Simulate mouse click
    mgr._last_input_keyboard = False
    assert focus_reason() == Qt.FocusReason.MouseFocusReason
    # Simulate keyboard
    mgr._last_input_keyboard = True
    assert focus_reason() == Qt.FocusReason.OtherFocusReason
    # reset
    mgr._last_input_keyboard = True


def test_nav_graph_snapshot_and_validate(qapp):
    from sli_ui_toolkit.ui.managers.nav_graph import snapshot, validate

    graph = snapshot()
    # Validate should be clean (POC checks ref_x and extra_keys)
    violations = validate(graph)
    assert not violations, f"nav_graph violations: {violations}"


def test_tab_strip_left_right_requires_enter(qapp):
    from sli_ui_toolkit.widgets import AdaptiveTabStrip

    strip = AdaptiveTabStrip(add_icon="add", close_icon="remove")
    strip.addTab("A")
    strip.addTab("B")
    strip.addTab("C")
    strip.setCurrentIndex(0)
    strip.resize(600, strip.sizeHint().height())
    strip.show()
    qapp.processEvents()

    bar = strip.tab_bar
    # Focus the bar as keyboard (OtherFocusReason) — ring visible
    bar.setFocus(Qt.FocusReason.OtherFocusReason)
    qapp.processEvents()
    assert bar._focused_index == 0

    # Left/Right should move focused, not current
    bar._focused_index = 0
    bar._move_focus(1)
    assert bar._focused_index == 1
    assert bar.currentIndex() == 0, "Left/Right must not switch tab without Enter"
    bar._move_focus(1)
    assert bar._focused_index == 2
    assert bar.currentIndex() == 0

    # Enter activates
    bar._activate_focused()
    assert bar.currentIndex() == 2
    assert bar._focused_index == 2

    # Home/End
    bar._focused_index = 1
    bar._focused_index = 0  # simulate Home
    assert bar._focused_index == 0
    strip.hide()


def test_tab_strip_entry_lands_without_switching_tab(qapp):
    """Entering the strip must only land the keyboard cursor — switching the
    active tab is activation and must require Enter/Space, the same contract
    ``test_tab_strip_left_right_requires_enter`` pins for Left/Right.

    ``TabStripSection.focus_first``/``focus_last`` are the entry points for
    every cross-section hand-off into the strip (Down from the title bar, Up
    from the session picker, ``focus_last`` after a tab closes).  They used to
    run ``setCurrentIndex()`` on the nearest tab, so merely *arriving* switched
    the active workspace session with no Enter — ``currentChanged`` fires and
    the app switches sessions from it.
    """
    from core.navigation_sections import TabStripSection
    from ui.icon_manager import AppIcon
    from ui.widgets.workspace_tab_strip import WorkspaceTabStrip

    strip = WorkspaceTabStrip(add_icon=AppIcon.ADD, close_icon=AppIcon.CLOSE)
    for title in ("A", "B", "C"):
        strip.addTab(title)
    strip.setCurrentIndex(0)
    strip.resize(700, strip.sizeHint().height())
    strip.show()
    qapp.processEvents()

    switched: list[int] = []
    strip.currentChanged.connect(switched.append)

    # ref_x over the *second* tab — what Up-from-picker / Down-from-title-bar
    # hand over (the nearest-tab branch of ``_focus_nearest``).
    ref_x = strip.tab_bar.mapToGlobal(strip.tab_bar.tabRect(1).center()).x()
    section = TabStripSection(strip)
    for entry in (section.focus_last, section.focus_first):
        assert entry(ref_x=ref_x, reason=Qt.FocusReason.OtherFocusReason) is True

    assert switched == [], (
        "focusing the tab strip switched the active tab; activation must "
        "require Enter/Space"
    )
    assert strip.currentIndex() == 0
    # …but the keyboard cursor still lands on the nearest tab (the ring).
    assert strip.tab_bar._focused_index == 1
    # And the add button the report named stays inert on focus + arrows.
    add_fired: list[int] = []
    strip.addRequested.connect(add_fired.append)
    assert section.focus_last(reason=Qt.FocusReason.OtherFocusReason) is True
    assert QApplication.focusWidget() is strip.add_button
    for key in (Qt.Key.Key_Down, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Left):
        strip.add_button.setFocus(Qt.FocusReason.OtherFocusReason)
        strip.add_button.keyPressEvent(
            QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier)
        )
    assert add_fired == []
    strip.hide()
