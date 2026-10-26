"""The magnifier transients wire their event filter exactly once per widget.

Regression (owner log, 2026-10-26): ``[magnifier-visibility] btn_magnifier
event=8 reason=FocusReason.MouseFocusReason`` arrived in identical pairs with
the same timestamp — one focus event handled (and logged) twice. Qt does *not*
dedupe a second ``installEventFilter`` of the same *object*, but it also does
not deliver twice for it, so a duplicate pair can only come from a **second
filter object** on the same button: the controller resolved twice for one
widget (page rebuilt under a fresh ``UIManager``/``TransientUIManager``) stacks
a second host alongside the first, and each host dispatches to its own
controller.

The fix is ownership, not a guard in the handler: the installation is recorded
on the widget in a private attribute, a later controller tears the
previous one down before installing its own (``release_wiring`` then
``bind_wiring``), and ``teardown()`` removes filters *and* disconnects signals
so nothing outlives the controller that owns it.
"""

from __future__ import annotations

from types import SimpleNamespace

from PySide6.QtCore import QEvent, QObject, Qt, Signal
from PySide6.QtGui import QFocusEvent
from PySide6.QtWidgets import QApplication, QWidget

import tabs.image_compare.ui.transient_magnifier as tm
import tabs.image_compare.ui.transient_magnifier_instances as tmi


class _ToggleButton(QWidget):
    toggled = Signal(bool)


class _FakeFlyout(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.hide_calls = 0
        self.scheduled: list[int] = []
        self.btn_left = QWidget(self)
        self.btn_center = QWidget(self)
        self.btn_right = QWidget(self)

    def hide(self) -> None:
        self.hide_calls += 1
        super().hide()

    def show_for_button(self, *_args, **_kwargs) -> None:
        self.show()

    def schedule_auto_hide(self, ms: int) -> None:
        self.scheduled.append(ms)

    def cancel_auto_hide(self) -> None:
        pass

    def set_mode_and_states(self, *_args, **_kwargs) -> None:
        pass


class _Host(QObject):
    """Stands in for ``TransientUIManager``: owns the filter, dispatches."""

    def __init__(self, parent=None):
        super().__init__(parent if isinstance(parent, QObject) else None)
        self.store = SimpleNamespace()
        self.parent_widget = parent
        self._magn_popup_open = False
        self._magn_popup_last_open_ts = 0.0
        self._magn_instances_popup_open = False
        self.controller = None
        self.deliveries = 0

    def eventFilter(self, watched, event) -> bool:  # noqa: N802 - Qt override
        self.deliveries += 1
        controller = self.controller
        if controller is None:
            return False
        return bool(controller.event_filter(watched, event))


class _InstancesStub:
    def hide(self) -> None:
        pass


class _Manager:
    def __init__(self, host):
        self.host = host
        self.panel_instances = _InstancesStub()


def _make_visibility_widget():
    root = QWidget()
    button = _ToggleButton(root)
    flyout = _FakeFlyout(root)
    widget = SimpleNamespace(
        btn_magnifier=button,
        magnifier_visibility_flyout=flyout,
    )
    # Keep the container alive: the namespace only holds the children, and a
    # parentless root would be collected with them.
    widget._root = root
    return widget, button, flyout


def _focus_in(button) -> None:
    """Deliver one FocusIn without touching the focus chain of a hidden tree."""
    QApplication.instance().notify(
        button, QFocusEvent(QEvent.Type.FocusIn, Qt.FocusReason.MouseFocusReason)
    )


def _visibility_controller(monkeypatch, widget):
    # No store in this stand: the overlay capability query must resolve to
    # "magnifier off" so show() is a no-op and the wiring is the only variable.
    monkeypatch.setattr(tm, "_query_overlay", lambda _store, _cap, default=None: default)
    host = _Host(widget)
    controller = tm.MagnifierVisibilityController(_Manager(host), widget)
    host.controller = controller
    return host, controller


def test_one_focus_event_reaches_one_controller(qapp, monkeypatch):
    widget, button, _flyout = _make_visibility_widget()
    host_a, controller_a = _visibility_controller(monkeypatch, widget)
    host_b, controller_b = _visibility_controller(monkeypatch, widget)
    assert controller_a is not controller_b

    _focus_in(button)

    deliveries = host_a.deliveries + host_b.deliveries
    assert deliveries == 1, (
        f"one synthetic FocusIn reached {deliveries} controllers "
        f"({host_a.deliveries} + {host_b.deliveries}) — a second filter is "
        "still installed on btn_magnifier"
    )


def test_toggled_is_not_delivered_twice(qapp, monkeypatch):
    widget, button, flyout = _make_visibility_widget()
    _visibility_controller(monkeypatch, widget)
    _visibility_controller(monkeypatch, widget)

    button.toggled.emit(False)

    assert flyout.hide_calls == 1, (
        f"toggled(False) hid the flyout {flyout.hide_calls} times — the "
        "signal is connected once per controller"
    )


def test_teardown_detaches_filters_and_signal(qapp, monkeypatch):
    widget, button, flyout = _make_visibility_widget()
    host, controller = _visibility_controller(monkeypatch, widget)

    controller.teardown()
    _focus_in(button)
    assert host.deliveries == 0, "a torn-down controller still receives events"

    button.toggled.emit(False)
    assert flyout.hide_calls == 0, "a torn-down controller still reacts to toggled"


def test_rewire_through_the_same_host_keeps_its_filter(qapp, monkeypatch):
    """Takeover must release *before* installing: with the same host object a
    release-after-install would remove the filter just installed and leave the
    button deaf."""
    widget, button, _flyout = _make_visibility_widget()
    host, first = _visibility_controller(monkeypatch, widget)
    second = tm.MagnifierVisibilityController(_Manager(host), widget)
    host.controller = second

    _focus_in(button)

    assert host.deliveries == 1, "the surviving filter no longer sees the button"
    first.teardown()
    _focus_in(button)
    assert host.deliveries == 2, "torn-down first controller took the live filter with it"


class _BubbleStub:
    instances: list["_BubbleStub"] = []

    def __init__(self, **_kwargs) -> None:
        self.hide_calls = 0
        self.show_calls = 0
        self.restart_calls = 0
        _BubbleStub.instances.append(self)

    def show(self, **_kwargs) -> bool:
        self.show_calls += 1
        return False

    def hide(self) -> None:
        self.hide_calls += 1

    def restart_auto_hide(self) -> None:
        self.restart_calls += 1


class _Counter(QWidget):
    countChanged = Signal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._count = 2

    def magnifier_count(self) -> int:
        return self._count

    def popup_targets(self):
        return (self,)


def test_instances_controller_takes_over_too(qapp, monkeypatch):
    monkeypatch.setattr(tmi, "AnchoredPopupBubbleController", _BubbleStub)
    _BubbleStub.instances = []
    root = QWidget()
    button = _Counter(root)
    widget = SimpleNamespace(btn_magnifier_instances=button)

    host_a = _Host(widget)
    controller_a = tmi.MagnifierInstancesPopupController(_Manager(host_a), widget)
    host_a.controller = controller_a
    host_b = _Host(widget)
    controller_b = tmi.MagnifierInstancesPopupController(_Manager(host_b), widget)
    host_b.controller = controller_b

    _focus_in(button)
    deliveries = host_a.deliveries + host_b.deliveries
    assert deliveries == 1, (
        f"one synthetic FocusIn reached {deliveries} instance controllers"
    )

    button._count = 1
    button.countChanged.emit(1)
    hidden = sum(bubble.hide_calls for bubble in _BubbleStub.instances)
    assert hidden == 1, (
        f"countChanged(1) ran on_count_changed {hidden} times — the signal "
        "is connected once per controller"
    )
