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
    # The backstop is the controller's own re-validating timer (the flyout's
    # auto-hide hid a panel that sat under a stationary cursor — 2026-10-26).
    assert controller._backstop.is_active(), "backstop timer must be armed on linked transition"
    assert flyout.hide_calls == 0, "must not hide while cursor is on a linked sibling"


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

    assert controller._backstop.is_active(), "backstop must be armed on rim Leave"
    assert flyout.hide_calls == 0, "rim Leave must not hide immediately"

class _FakeDropOverlay(QWidget):
    """Stand-in for ``ComboBox._DropdownOverlay``: a BaseFlyout **child overlay**
    (not a popup window) anchored to a control inside the unit."""

    def __init__(self, anchors, parent=None):
        super().__init__(parent)
        self._anchors = tuple(anchors)

    def anchor_widgets(self):
        return self._anchors

    def contains_global(self, _global_pos) -> bool:
        return True


def test_cursor_over_the_combobox_dropdown_stays_inside_the_unit(qapp, monkeypatch):
    """Regression (owner, 2026-10-26): opening the interpolation list collapsed
    the panel and the list itself.

    The list is a toolkit combo dropdown — an in-window ``BaseFlyout`` overlay
    anchored to a control INSIDE the panel, not a Qt popup window and not a
    FlyoutManager ``linked_child`` of the panel. ``_combined_reason`` therefore
    reported ``hover-move:outside`` and the panel hid immediately (measured in
    the live journal: ``show`` -> ``hover-move:outside`` -> ``hide:immediate``).
    """
    fw, controller = _make_controller(qapp, monkeypatch, cursor_global=QPoint(0, 0))
    flyout = fw.magnifier_settings_flyout
    flyout.show()
    monkeypatch.setattr(flyout, "isVisible", lambda: True)

    overlay = _FakeDropOverlay(anchors=(fw.magnifier_group_container,), parent=fw)
    row = QWidget(overlay)  # the widget actually under the cursor
    overlay.show()
    monkeypatch.setattr(transient.QApplication, "widgetAt", staticmethod(lambda _pos: row))
    monkeypatch.setattr(
        transient.QApplication, "activePopupWidget", staticmethod(lambda: None)
    )
    monkeypatch.setattr(transient.QCursor, "pos", staticmethod(lambda: QPoint(900, 900)))

    assert controller._combined_reason() == "overlay"

    flyout.hide_calls = 0
    controller._handle_hover_event(QEvent(QEvent.Type.HoverMove))
    assert flyout.hide_calls == 0, "panel must not hide while the cursor is on the list"


def test_focus_inside_the_dropdown_keeps_the_panel(qapp, monkeypatch):
    """Picking an entry moves focus into the list; that focus is still our unit."""
    fw, controller = _make_controller(qapp, monkeypatch, cursor_global=QPoint(0, 0))
    flyout = fw.magnifier_settings_flyout
    flyout.show()
    monkeypatch.setattr(flyout, "isVisible", lambda: True)

    overlay = _FakeDropOverlay(anchors=(fw.magnifier_group_container,), parent=fw)
    row = QWidget(overlay)
    overlay.show()
    monkeypatch.setattr(
        transient.QApplication, "focusWidget", staticmethod(lambda: row)
    )
    monkeypatch.setattr(
        transient.QApplication, "activePopupWidget", staticmethod(lambda: None)
    )

    flyout.hide_calls = 0
    controller._handle_button_focus_event(
        QFocusEvent(QEvent.Type.FocusOut, Qt.FocusReason.MouseFocusReason)
    )
    assert flyout.hide_calls == 0, "focus inside the dropdown must keep the panel"


def test_backstop_does_not_hide_while_the_cursor_is_still_inside(qapp, monkeypatch):
    """Regression (owner, 2026-10-26): the panel closed itself ~300 ms after
    showing, under a stationary cursor, and took the interpolation list with it.

    Journal: ``hide:schedule-backstop cursor=1324,500`` -> 300 ms ->
    ``timeout:hide MagnifierSettingsFlyout cursor=1343,875`` — the cursor was on
    the panel body all along, no later event cancelled the timer. The backstop
    must re-validate before hiding.
    """
    fw, controller = _make_controller(qapp, monkeypatch, cursor_global=QPoint(0, 0))
    flyout = fw.magnifier_settings_flyout
    flyout.show()
    monkeypatch.setattr(flyout, "isVisible", lambda: True)
    # Cursor sits on the panel body when the backstop fires.
    on_panel = fw.checkbox_widget.mapToGlobal(QPoint(10, 10))
    monkeypatch.setattr(transient.QCursor, "pos", staticmethod(lambda: on_panel))
    monkeypatch.setattr(flyout, "contains_global", lambda _pos: True)

    flyout.hide_calls = 0
    controller._hide_if_outside()
    assert flyout.hide_calls == 0, "panel must not hide while the cursor is on it"


def test_backstop_hides_when_the_cursor_really_left(qapp, monkeypatch):
    """The orphan-open guard still works: outside the unit at timeout -> hide."""
    fw, controller = _make_controller(qapp, monkeypatch, cursor_global=QPoint(0, 0))
    flyout = fw.magnifier_settings_flyout
    flyout.show()
    monkeypatch.setattr(flyout, "isVisible", lambda: True)
    far = fw.checkbox_widget.mapToGlobal(QPoint(4000, 4000))
    monkeypatch.setattr(transient.QCursor, "pos", staticmethod(lambda: far))
    monkeypatch.setattr(flyout, "contains_global", lambda _pos: False)

    flyout.hide_calls = 0
    controller._hide_if_outside()
    assert flyout.hide_calls >= 1, "an orphan-open guard must still hide outside"
