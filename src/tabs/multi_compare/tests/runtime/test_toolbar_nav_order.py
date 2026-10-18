"""Multi-compare toolbar keyboard-traversal order (keyboard-nav plan D2).

The toolbar builds its buttons with ``parent=self`` and only afterwards
reparents them into group containers, so the ``findChildren`` (QObject
construction/reparent) order is NOT the visual order: ``btn_add`` is
constructed before the group containers exist and remains their sibling,
while every other button is nested inside its container — a raw child
walk therefore visits ``btn_add`` first even though it renders between
the label group and the action group. The toolkit's ``ToolbarRowsSection``
sorts keyboard-focusable children by on-screen x for exactly this reason;
this test pins that order contract against the real, laid-out toolbar:

- the documented visual order of the active (beginner) layout mode is
  ``divider_visible, divider_color, divider_width, text_settings, add,
  quick_save`` — asserted as strictly increasing screen-x centers;
- the raw ``findChildren`` order diverges from it (the fragility the
  screen-x sort exists to paper over);
- a real Left/Right traversal through the toolkit section moves focus to
  the visually adjacent button, not the ``findChildren`` neighbour:
  Right from ``btn_add`` lands on ``btn_quick_save``, never on
  ``btn_divider_visible``.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget

from sli_ui_toolkit.ui.managers import NavigationManager
from sli_ui_toolkit.ui.managers.navigation_sections import ToolbarRowsSection

from tabs.multi_compare.ui.toolbar import MultiCompareToolbar


def _visible_strong_focus(widget: QWidget) -> list[QWidget]:
    """Keyboard-focusable descendants in raw findChildren order (no sort)."""
    return [
        c
        for c in widget.findChildren(QWidget)
        if c.focusPolicy() == Qt.FocusPolicy.StrongFocus
        and c.isVisible()
        and c.isEnabled()
    ]


def _shown_toolbar(qapp) -> MultiCompareToolbar:
    """Real toolbar in the pinned active layout mode, laid out on screen."""
    toolbar = MultiCompareToolbar()
    # Pin the active layout mode (beginner is the default): all six
    # visible controls, groups unrecomposed.
    toolbar.apply_ui_mode("beginner")
    toolbar.resize(900, 44)
    toolbar.show()
    QTest.qWait(50)  # let layout settle so mapToGlobal returns real geometry
    return toolbar


def test_toolbar_screen_x_order_matches_documented_visual_order(qapp):
    toolbar = _shown_toolbar(qapp)
    try:
        visual_order = [
            toolbar.btn_divider_visible,
            toolbar.btn_divider_color,
            toolbar.btn_divider_width,
            toolbar.btn_text_settings,
            toolbar.btn_add,
            toolbar.btn_quick_save,
        ]
        xs = [w.mapToGlobal(w.rect().center()).x() for w in visual_order]
        assert all(a < b for a, b in zip(xs, xs[1:]))

        # The findChildren order is NOT the visual order for this toolbar —
        # the divergence the toolkit's screen-x sort exists to paper over.
        assert _visible_strong_focus(toolbar) != visual_order
    finally:
        toolbar.deleteLater()


def test_toolbar_right_traversal_follows_visual_order(qapp):
    toolbar = _shown_toolbar(qapp)
    try:
        manager = NavigationManager.get_instance()
        section = ToolbarRowsSection(lambda: [toolbar], tag="mc-order-test")
        manager.register(toolbar, section)
        try:
            toolbar.btn_add.setFocus(Qt.FocusReason.OtherFocusReason)
            QTest.qWait(20)
            assert section.navigate(Qt.Key.Key_Right, toolbar.btn_add) is True
            QTest.qWait(20)
            focused = QApplication.focusWidget()
            assert focused is toolbar.btn_quick_save  # visually right of add
            assert focused is not toolbar.btn_divider_visible  # findChildren neighbour
        finally:
            manager.unregister(toolbar)
    finally:
        toolbar.deleteLater()
