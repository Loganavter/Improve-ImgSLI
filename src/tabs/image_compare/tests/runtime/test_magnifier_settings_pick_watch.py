"""After a child-list pick the panel must still be closable by leaving it.

Owner report 2026-10-28: "after choosing an interpolation the loupe's panel never
closes, even when the mouse goes to the other end of the screen".

The pick closes the interpolation list, and that used to *cancel* the panel's
pending hide (so the pick is not cut off) without arming anything else. The list
is a separate surface with no event filter of its own (see
``_combined_reason``'s "linked" branch), so when it closes under the cursor no
later Enter/Leave reaches the panel: nothing re-armed and nothing ever hid it.

Fix under test: ``note_child_pick_closed()`` cancels and then arms the backstop,
whose action re-validates the cursor and re-arms itself while the cursor is
still inside the unit.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QWidget

import tabs.image_compare.ui.transient_magnifier_settings as transient

DELAY = transient.AppConstants.TRANSIENT_AUTO_HIDE_DELAY_MS


class _FakeFlyout(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.hide_calls = 0
        self.cancel_calls = 0
        self.contains = False

    def cancel_auto_hide(self):
        self.cancel_calls += 1

    def schedule_auto_hide(self, _ms: int):
        pass

    def show_for_group(self, _group):
        pass

    def contains_global(self, _pos) -> bool:
        return self.contains

    def hide(self) -> None:
        self.hide_calls += 1
        super().hide()


class _FakeWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.checkbox_widget = QWidget(self)
        self.magnifier_group_container = QWidget(self.checkbox_widget)
        self.magnifier_settings_flyout = _FakeFlyout(self.checkbox_widget)


def _controller(qapp, monkeypatch, cursor: QPoint):
    fw = _FakeWidget()
    fw.checkbox_widget.setGeometry(0, 0, 600, 80)
    fw.magnifier_group_container.setGeometry(50, 10, 200, 60)
    fw.show()
    fw.checkbox_widget.show()
    fw.magnifier_settings_flyout.show()
    fw.magnifier_settings_flyout.hide_calls = 0
    qapp.processEvents()
    monkeypatch.setattr(transient.QCursor, "pos", staticmethod(lambda: cursor))
    return fw, transient.MagnifierSettingsHoverController(fw)


def test_pick_then_leaving_the_unit_closes_the_panel(qapp, monkeypatch):
    """The reported bug: the pin must not be permanent."""
    inside_panel = QPoint(5, 5)
    fw, controller = _controller(qapp, monkeypatch, cursor=inside_panel)
    flyout = fw.magnifier_settings_flyout
    flyout.contains = True  # cursor sits on the panel body after the pick

    controller._cancel_settings_auto_hide()
    qapp.processEvents()
    assert flyout.cancel_calls >= 1, "the pick must cancel the pending immediate hide"
    assert flyout.hide_calls == 0, "the pick must not close the panel under the user"

    # Cursor goes to the far end of the screen: nothing else will ever fire.
    flyout.contains = False
    monkeypatch.setattr(
        transient.QCursor, "pos", staticmethod(lambda: QPoint(1900, 1300))
    )
    QTest.qWait(DELAY + 250)

    assert flyout.hide_calls == 1, (
        f"panel still open after the cursor left ({flyout.hide_calls} hides): "
        "the post-pick cancel pinned it — arm a re-validating backstop instead"
    )


def test_pick_while_the_cursor_stays_inside_keeps_the_panel_open(qapp, monkeypatch):
    """The other half of the contract: the pick itself must not cut the panel."""
    fw, controller = _controller(qapp, monkeypatch, cursor=QPoint(5, 5))
    flyout = fw.magnifier_settings_flyout
    flyout.contains = True

    controller._cancel_settings_auto_hide()
    qapp.processEvents()
    QTest.qWait(DELAY + 250)

    assert flyout.hide_calls == 0, (
        "the panel closed while the cursor was still on it: the post-pick watch "
        "must re-arm instead of hiding"
    )


def test_a_real_hover_takes_the_watch_over(qapp, monkeypatch):
    """Returning to the unit ends the watch (event-driven lifecycle resumes)."""
    fw, controller = _controller(qapp, monkeypatch, cursor=QPoint(5, 5))
    flyout = fw.magnifier_settings_flyout
    flyout.contains = True

    controller._cancel_settings_auto_hide()
    assert controller._orphan_watch is True

    controller._cancel_hide()
    assert controller._orphan_watch is False, (
        "the post-pick watch survived a real hover/focus return — it would keep "
        "polling the cursor for the whole lifetime of the panel"
    )
