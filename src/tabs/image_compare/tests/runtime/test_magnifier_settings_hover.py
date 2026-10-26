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

from PySide6.QtCore import QEvent, QPoint, Qt
from PySide6.QtGui import QFocusEvent
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
    fw.show()
    fw.checkbox_widget.show()
    # Panel starts hidden in production (overlay attach hides it); showing
    # the fake tree would otherwise leave it visible and Enter becomes a
    # no-op cancel instead of a show.
    fw.magnifier_settings_flyout.hide()
    fw.magnifier_settings_flyout.hide_calls = 0
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
    qapp.notify(group, _hover_event(QEvent.Type.HoverEnter, center))
    assert fw.magnifier_settings_flyout.shown_for == [group]

    # Leaving to dead space hides immediately.
    outside = group.mapToGlobal(QPoint(-100, -100))
    monkeypatch.setattr(transient.QCursor, "pos", staticmethod(lambda: outside))
    fw.magnifier_settings_flyout.show()
    qapp.notify(group, _hover_event(QEvent.Type.HoverLeave, center))
    assert fw.magnifier_settings_flyout.hide_calls == 1


def test_toolbar_fringe_within_padding_triggers(qapp, monkeypatch):
    pad = transient._HOVER_ZONE_PADDING_PX
    fw, controller = _make_controller(
        qapp, monkeypatch, cursor_global=QPoint(0, 0)
    )
    group = fw.magnifier_group_container
    fringe = group.mapToGlobal(QPoint(-pad, 30))
    monkeypatch.setattr(transient.QCursor, "pos", staticmethod(lambda: fringe))

    qapp.notify(
        fw.checkbox_widget, _hover_event(QEvent.Type.HoverEnter, fringe)
    )
    assert fw.magnifier_settings_flyout.shown_for

    far = group.mapToGlobal(QPoint(-pad - 30, 30))
    monkeypatch.setattr(transient.QCursor, "pos", staticmethod(lambda: far))
    fw.magnifier_settings_flyout.show()
    qapp.notify(
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

    qapp.notify(group, _hover_event(QEvent.Type.HoverLeave, linked_pos))
    assert flyout.schedule_calls, "backstop timer must be armed on linked transition"
    assert flyout.hide_calls == 0, "must not hide while cursor is on a linked sibling"
    assert flyout.isVisible()


class _FakeManager:
    def linked_children(self, _flyout):
        return (_FakeLinkedChild(),)


def test_keyboard_focus_on_guides_button_opens_panel(qapp, monkeypatch):
    """Regression: btn_magnifier_guides was skipped in _wire (continue), so
    keyboard focus on the laser button neither opened the panel, nor counted
    as inside on FocusOut from a sibling (an open panel hid on Tab-onto it),
    nor got the Down-link into the panel."""
    from sli_ui_toolkit import managers as _managers

    bound: list[tuple] = []
    monkeypatch.setattr(
        _managers,
        "bind_group_flyout",
        lambda group, flyout, **kwargs: bound.append(
            (group, flyout, kwargs.get("side"))
        ),
    )
    fw = _FakeWidget()
    fw.checkbox_widget.setGeometry(0, 0, 600, 80)
    fw.magnifier_group_container.setGeometry(50, 10, 200, 60)
    guides = QWidget(fw.magnifier_group_container)
    guides.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    fw.btn_magnifier_guides = guides
    # A top button (above-flyout owner): its below-link must coexist with
    # the above-link instead of overwriting it (per-side registry).
    top = QWidget(fw.magnifier_group_container)
    top.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    fw.btn_magnifier = top
    fw.show()
    fw.magnifier_settings_flyout.hide()
    qapp.processEvents()
    monkeypatch.setattr(transient.QCursor, "pos", staticmethod(lambda: QPoint(0, 0)))
    controller = transient.MagnifierSettingsHoverController(fw)

    assert guides in controller._group_buttons
    assert top in controller._group_buttons
    # One group-level registration serves every member (no per-child bind
    # loop): the manager resolves it for whichever member is focused.
    assert bound == [
        (fw.magnifier_group_container, fw.magnifier_settings_flyout, "below")
    ]

    controller.eventFilter(
        guides, QFocusEvent(QEvent.Type.FocusIn, Qt.FocusReason.TabFocusReason)
    )
    assert fw.magnifier_settings_flyout.shown_for == [fw.magnifier_group_container]


def test_leave_in_padding_rim_arms_backstop(qapp, monkeypatch):
    """Leave fires on widget exit; the sampled cursor may still sit in the
    ±10px padding rim (pos lags the boundary crossing, and no second Leave
    fires for the rim itself). A bare cancel here orphans the panel when
    the cursor keeps traveling through unwatched space (canvas, native
    CSD) — arm the backstop timer instead."""
    pad = transient._HOVER_ZONE_PADDING_PX
    fw, controller = _make_controller(
        qapp, monkeypatch, cursor_global=QPoint(0, 0)
    )
    group = fw.magnifier_group_container
    flyout = fw.magnifier_settings_flyout
    flyout.show()
    rim = group.mapToGlobal(QPoint(-pad, 30))
    monkeypatch.setattr(transient.QCursor, "pos", staticmethod(lambda: rim))

    qapp.notify(group, QEvent(QEvent.Type.Leave))

    assert flyout.schedule_calls, "backstop must be armed on rim Leave"
    assert flyout.isVisible()

class _FakePopup(QWidget):
    """Stand-in for a toolkit combo dropdown (``BaseFlyout`` popup)."""

    def __init__(self, anchors, parent=None):
        super().__init__(parent)
        self._anchors = tuple(anchors)

    def anchor_widgets(self):
        return self._anchors

    def contains_global(self, global_pos) -> bool:
        # The popup owns the whole screen in this stand: any probe point is
        # "over the list" once the test says so.
        return True


def test_cursor_over_the_combobox_dropdown_stays_inside_the_unit(qapp, monkeypatch):
    """Regression (owner, 2026-10-26): opening the interpolation list collapsed
    the panel and the list itself.

    The list is a combo popup anchored to a control INSIDE the panel, but it is
    not a FlyoutManager ``linked_child`` of the panel, so ``_combined_reason``
    reported ``hover-move:outside`` and the panel hid immediately (measured in
    the live journal). A popup opened from inside the unit must count as inside.
    """
    fw, controller = _make_controller(qapp, monkeypatch, cursor_global=QPoint(0, 0))
    flyout = fw.magnifier_settings_flyout
    flyout.show()

    popup = _FakePopup(anchors=(fw.magnifier_group_container,), parent=fw)
    popup.show()
    monkeypatch.setattr(popup, "isVisible", lambda: True)
    monkeypatch.setattr(flyout, "isVisible", lambda: True)
    monkeypatch.setattr(
        transient.QApplication, "activePopupWidget", staticmethod(lambda: popup)
    )
    over_list = popup.mapToGlobal(QPoint(10, 10))
    monkeypatch.setattr(transient.QCursor, "pos", staticmethod(lambda: over_list))

    assert controller._combined_reason() == "popup"

    # Drive the decision directly: the synthetic popup is not a real Qt popup,
    # so event delivery through qapp.notify() would exercise the compositor
    # (and an offscreen stand has none). The handler is the unit under test.
    flyout.hide_calls = 0
    controller._handle_hover_event(QEvent(QEvent.Type.HoverMove))
    assert flyout.hide_calls == 0, "panel must not hide while the cursor is on the list"
    assert controller._combined_reason() == "popup"


def test_focus_inside_the_dropdown_keeps_the_panel(qapp, monkeypatch):
    """Picking an entry focuses the list; that focus is still our unit."""
    fw, controller = _make_controller(qapp, monkeypatch, cursor_global=QPoint(0, 0))
    flyout = fw.magnifier_settings_flyout
    flyout.show()

    popup = _FakePopup(anchors=(fw.magnifier_group_container,), parent=fw)
    item = QWidget(popup)
    popup.show()
    monkeypatch.setattr(popup, "isVisible", lambda: True)
    monkeypatch.setattr(flyout, "isVisible", lambda: True)
    monkeypatch.setattr(
        transient.QApplication, "activePopupWidget", staticmethod(lambda: popup)
    )
    monkeypatch.setattr(
        transient.QApplication, "focusWidget", staticmethod(lambda: item)
    )

    flyout.hide_calls = 0
    controller._handle_button_focus_event(
        QFocusEvent(QEvent.Type.FocusOut, Qt.FocusReason.MouseFocusReason)
    )
    assert flyout.hide_calls == 0, "focus inside the dropdown must keep the panel"

