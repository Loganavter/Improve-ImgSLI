"""Navigation graph contract — POC for navigation-robustness-plan.

Covers the two recent focus-ring/tab-strip fixes so they can't regress
without a test failure, instead of requiring log.txt triage.

Dogma source: docs/dev/investigations/navigation-robustness-plan.md,
sli_ui_toolkit/.../nav_graph.py, FILE_SIZE_POLICY.md precedent.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt


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
