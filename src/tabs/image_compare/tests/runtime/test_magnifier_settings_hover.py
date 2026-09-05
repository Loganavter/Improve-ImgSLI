"""Magnifier settings flyout hover trigger is scoped to a padded zone.

Regression: the flyout previously opened on any hover over the whole
toolbar row (``checkbox_widget``). It must open only when the cursor is
inside ``magnifier_group_container`` or within the padding around it.

Open/close is binary (no open timer, no close delay): entering the zone
shows immediately, leaving it hides immediately — except when the cursor
rests on the panel body or a linked sibling, where a backstop timer is
armed instead (leaving to an unwatched surface from there must still
close the panel; see test_leave_to_linked_child_arms_backstop).
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QPoint
from PySide6.QtWidgets import QWidget

import tabs.image_compare.ui.transient_magnifier_settings as transient


class _FakeFlyout(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.schedule_calls: list[int] = []
        self.cancel_calls = 0
        self.shown_for: list = []
        self.hide_calls = 0

    def cancel_auto_hide(self):
        self.cancel_calls += 1

    def schedule_auto_hide(self, ms: int):
        self.schedule_calls.append(ms)

    def show_for_group(self, group):
        self.shown_for.append(group)

    def contains_global(self, _pos) -> bool:
        return False

    def hide(self) -> None:
        self.hide_calls += 1
        super().hide()


class _FakeWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.checkbox_widget = QWidget(self)
        self.magnifier_group_container = QWidget(self.checkbox_widget)
        self.magnifier_settings_flyout = _FakeFlyout(self.checkbox_widget)


def _make_controller(qapp, monkeypatch, cursor_global):
    fw = _FakeWidget()
    fw.checkbox_widget.setGeometry(0, 0, 600, 80)
    fw.magnifier_group_container.setGeometry(50, 10, 200, 60)
    fw.checkbox_widget.show()
    qapp.processEvents()
    monkeypatch.setattr(
        transient.QCursor, "pos", staticmethod(lambda: cursor_global)
    )
    controller = transient.MagnifierSettingsHoverController(fw)
    return fw, controller


def _hover_event(event_type: QEvent.Type, global_pos: QPoint) -> QEvent:
    return QEvent(event_type)


def test_zone_covers_group_and_padding_but_not_far_toolbar(qapp, monkeypatch):
    pad = transient._HOVER_ZONE_PADDING_PX
    fw, controller = _make_controller(
        qapp, monkeypatch, cursor_global=QPoint(0, 0)
    )
    group = fw.magnifier_group_container
    center = group.mapToGlobal(QPoint(100, 30))
    left_edge = group.mapToGlobal(QPoint(0, 30))

    for point in (center, left_edge, left_edge - QPoint(pad, 0)):
        monkeypatch.setattr(transient.QCursor, "pos", staticmethod(lambda p=point: p))
        assert controller._cursor_in_group_zone(), f"expected in-zone at {point}"

    outside = left_edge - QPoint(pad + 1, 0)
    monkeypatch.setattr(transient.QCursor, "pos", staticmethod(lambda: outside))
    assert not controller._cursor_in_group_zone(), f"expected out-of-zone at {outside}"


def test_hover_in_zone_starts_open_timer(qapp, monkeypatch):
    fw, controller = _make_controller(
        qapp, monkeypatch, cursor_global=QPoint(0, 0)
    )
    group = fw.magnifier_group_container
    center = group.mapToGlobal(QPoint(100, 30))
    monkeypatch.setattr(transient.QCursor, "pos", staticmethod(lambda: center))

    # Entering the zone opens immediately (binary, no open timer).
    qapp.sendEvent(group, _hover_event(QEvent.Type.HoverEnter, center))
    assert fw.magnifier_settings_flyout.shown_for == [group]

    # Leaving to dead space hides immediately.
    outside = group.mapToGlobal(QPoint(-100, -100))
    monkeypatch.setattr(transient.QCursor, "pos", staticmethod(lambda: outside))
    fw.magnifier_settings_flyout.show()
    qapp.sendEvent(group, _hover_event(QEvent.Type.HoverLeave, center))
    assert fw.magnifier_settings_flyout.hide_calls == 1


def test_toolbar_fringe_within_padding_triggers(qapp, monkeypatch):
    pad = transient._HOVER_ZONE_PADDING_PX
    fw, controller = _make_controller(
        qapp, monkeypatch, cursor_global=QPoint(0, 0)
    )
    group = fw.magnifier_group_container
    fringe = group.mapToGlobal(QPoint(-pad, 30))
    monkeypatch.setattr(transient.QCursor, "pos", staticmethod(lambda: fringe))

    qapp.sendEvent(
        fw.checkbox_widget, _hover_event(QEvent.Type.HoverEnter, fringe)
    )
    assert fw.magnifier_settings_flyout.shown_for

    far = group.mapToGlobal(QPoint(-pad - 30, 30))
    monkeypatch.setattr(transient.QCursor, "pos", staticmethod(lambda: far))
    fw.magnifier_settings_flyout.show()
    qapp.sendEvent(
        fw.checkbox_widget, _hover_event(QEvent.Type.HoverMove, far)
    )
    assert fw.magnifier_settings_flyout.hide_calls == 1


class _FakeLinkedChild:
    def isVisible(self) -> bool:
        return True

    def contains_global(self, _pos) -> bool:
        return True


def test_leave_to_linked_child_arms_backstop(qapp, monkeypatch):
    """Leaving the group onto a linked sibling (dropdown, color-options)
    must arm the backstop timer, not just cancel: the sibling carries no
    event filter of its own, so a bare cancel would orphan the panel open
    once the cursor moves on to an unwatched surface (native CSD chrome)."""
    fw, controller = _make_controller(
        qapp, monkeypatch, cursor_global=QPoint(0, 0)
    )
    group = fw.magnifier_group_container
    flyout = fw.magnifier_settings_flyout
    flyout.show()

    from sli_ui_toolkit import managers as _managers

    fake_manager = _FakeManager()
    monkeypatch.setattr(
        _managers.FlyoutManager, "get_instance", staticmethod(lambda: fake_manager)
    )
    linked_pos = group.mapToGlobal(QPoint(500, 300))
    monkeypatch.setattr(transient.QCursor, "pos", staticmethod(lambda: linked_pos))

    qapp.sendEvent(group, _hover_event(QEvent.Type.HoverLeave, linked_pos))
    assert flyout.schedule_calls, "backstop timer must be armed on linked transition"
    assert flyout.hide_calls == 0, "must not hide while cursor is on a linked sibling"
    assert flyout.isVisible()


class _FakeManager:
    def linked_children(self, _flyout):
        return (_FakeLinkedChild(),)