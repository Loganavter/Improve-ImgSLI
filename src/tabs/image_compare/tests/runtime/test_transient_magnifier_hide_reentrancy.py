"""``MagnifierVisibilityController.hide()`` must not re-enter itself.

Red-before (owner, 2026-10-28): picking another interpolation in the loupe's
list froze the whole app — no exception, nothing in ``log.txt``, GUI thread
never came back.

Measured with ``faulthandler`` (SIGUSR1 dump of the frozen process) — an exact
10-frame cycle repeated down the stack::

    BaseFlyout.hide -> _finish_hide -> _restore_focus_policies -> setFocus
      -> FocusOut -> UIManager.eventFilter -> TransientUIManager.event_filter
        -> MagnifierVisibilityController.event_filter
          -> _handle_button_event -> self.hide(reason="focus_out") -> same cycle

Closing the visibility flyout restores focus onto its anchor, that focus change
is delivered back into the FocusOut branch, and the branch asks for ``hide()``
again. The resulting ``RecursionError`` was swallowed by the broad
``except Exception`` in that branch, so the dive simply repeated forever: the
GUI thread burned its life in ``hide()`` (each iteration also formats a
traceback in the toolkit) and no line was ever logged.

The fix under test: the controller is inert inside its own ``hide()``
(``self._hiding`` latch), and the swallow is no longer silent.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from PySide6.QtCore import QEvent, QObject, Qt, Signal
from PySide6.QtGui import QFocusEvent
from PySide6.QtWidgets import QWidget

import tabs.image_compare.ui.transient_magnifier as tm


class _ToggleButton(QWidget):
    toggled = Signal(bool)


class _FakeFlyout(QWidget):
    """A flyout whose ``hide()`` re-delivers the FocusOut its real counterpart
    produces via ``_finish_hide -> _restore_focus_policies -> setFocus``."""

    def __init__(self, controller_holder, parent=None):
        super().__init__(parent)
        self.hide_calls = 0
        self.scheduled: list[int] = []
        self.btn_left = QWidget(self)
        self.btn_center = QWidget(self)
        self.btn_right = QWidget(self)
        self._holder = controller_holder

    def hide(self) -> None:  # noqa: N802 - Qt-ish name
        self.hide_calls += 1
        controller = self._holder.get("controller")
        button = self._holder.get("button")
        if controller is not None and button is not None:
            controller.event_filter(
                button,
                QFocusEvent(QEvent.Type.FocusOut, Qt.FocusReason.MouseFocusReason),
            )
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
    def __init__(self, parent=None):
        super().__init__(None)
        self.store = SimpleNamespace()
        self.parent_widget = parent
        self._magn_popup_open = False
        self._magn_popup_last_open_ts = 0.0

    def eventFilter(self, watched, event) -> bool:  # noqa: N802 - Qt override
        return False


class _InstancesStub:
    def hide(self) -> None:
        pass


class _Manager:
    def __init__(self, host):
        self.host = host
        self.panel_instances = _InstancesStub()


def _controller(monkeypatch):
    # No store in this stand: ``_query_overlay`` resolves to its default so the
    # only variable is the hide path.
    monkeypatch.setattr(tm, "_query_overlay", lambda _store, _cap, default=None: default)
    root = QWidget()
    button = _ToggleButton(root)
    holder: dict[str, object] = {"button": button}
    flyout = _FakeFlyout(holder, root)
    widget = SimpleNamespace(
        btn_magnifier=button,
        magnifier_visibility_flyout=flyout,
        _root=root,
    )
    controller = tm.MagnifierVisibilityController(_Manager(_Host(root)), widget)
    holder["controller"] = controller
    return controller, flyout


def test_hide_does_not_recursively_reenter_through_the_focus_restore(qapp, monkeypatch):
    """One ``hide()`` closes the flyout once — not once per focus round-trip."""
    controller, flyout = _controller(monkeypatch)

    controller.hide(reason="explicit")

    assert flyout.hide_calls == 1, (
        f"flyout.hide() ran {flyout.hide_calls} times for one controller.hide(): "
        "the FocusOut that the flyout's own focus restore produces re-entered "
        "hide() (the 2026-10-28 freeze; a swallowed RecursionError used to hide it)"
    )


def test_reentrant_hide_returns_without_touching_the_host(qapp, monkeypatch):
    """The nested call must be inert, not merely cheap: it may not clear the
    host latch or touch the flyout again."""
    controller, flyout = _controller(monkeypatch)
    host = controller.manager.host
    host._magn_popup_open = True

    def _reenter(_reason="explicit"):
        assert controller._hiding is True, "re-entered outside the hide window"
        controller.hide(reason="focus_out")

    flyout.hide = _reenter  # type: ignore[method-assign]

    controller.hide(reason="explicit")

    assert controller._hiding is False, "the latch must not survive the call"
    assert host._magn_popup_open is False


def test_hide_clears_the_latch_even_when_the_flyout_raises(qapp, monkeypatch):
    controller, flyout = _controller(monkeypatch)

    def _boom() -> None:
        raise RuntimeError("flyout exploded")

    flyout.hide = _boom  # type: ignore[method-assign]

    with pytest.raises(RuntimeError):
        controller.hide(reason="explicit")

    assert controller._hiding is False, (
        "a raising flyout.hide() left the latch set — every later hide() would "
        "be a silent no-op and the loupe panel would never close"
    )
