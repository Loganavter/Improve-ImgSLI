"""Closing the host window latches the magnifier transients off for good.

Regression (owner, live on merged ``main``, 2026-10-26): with the magnifier
enabled and a couple of actions done, closing the window left the process in
``QApplication.exec()`` while the console repeated

    [magnifier-visibility] btn_magnifier event=9 reason=FocusReason.MouseFocusReason

``event=9`` is ``QEvent.Type.FocusOut``, and the stream contains no matching
FocusIn: it is not an ordinary focus pair, it is a *loop*. Nothing tore the
transient controller down on shutdown — the window close path set
``window._closing`` and shut the presenter down, but ``UIManager`` /
``TransientUIManager`` and every event filter + hover timer installed through
them outlived it. Each late focus event then ran the whole reaction chain
(``hide()`` on FocusOut -> focus back to the button -> a FocusIn that re-armed
the hover timer -> the flyout re-opening) once per loop turn, forever.

The fix is a closing latch: ``MarkShuttingDownStep`` — the first step of the
window shutdown pipeline, i.e. *before* the steps that hide/close windows and
therefore still produce one last focus burst — asks the transient UI to shut
down, every controller stops reacting, and the wiring is torn down while Qt is
still healthy.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from PySide6.QtCore import QEvent, QObject, Qt, Signal
from PySide6.QtGui import QFocusEvent
from PySide6.QtWidgets import QApplication, QWidget

import tabs.image_compare.ui.transient_magnifier as tm
import tabs.image_compare.ui.transient_magnifier_instances as tmi
import ui.managers.transient_ui_manager as tum
from ui.main_window.lifecycle import MarkShuttingDownStep
from ui.managers.ui_manager import UIManager


# --------------------------------------------------------------------------
# stands (same shapes as test_transient_magnifier_wiring.py, deliberately)
# --------------------------------------------------------------------------


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
    """Stands in for ``UIManager``: owns the filter, dispatches to the controller."""

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


class _WindowStub(QWidget):
    """The host window the transients are wired through."""

    def __init__(self) -> None:
        super().__init__()
        self._closing = False


class _UIManagerStub:
    """``UIManager`` with the heavy construction skipped: only the shutdown
    path under test is real (the production body is called unbound — it only
    touches ``self.transient``)."""

    def __init__(self, transient) -> None:
        self.transient = transient

    def shutdown(self) -> None:
        method = getattr(UIManager, "shutdown", None)
        if callable(method):
            method(self)


def _transient_manager(monkeypatch, host):
    # ``PopupClosingController.__init__`` runs a full TabRegistry discovery;
    # it plays no part in the latch, so keep it out of the stand.
    monkeypatch.setattr(tum, "PopupClosingController", lambda _manager: SimpleNamespace())
    return tum.TransientUIManager(host)


def _make_visibility_widget():
    root = QWidget()
    button = _ToggleButton(root)
    flyout = _FakeFlyout(root)
    widget = SimpleNamespace(
        btn_magnifier=button,
        magnifier_visibility_flyout=flyout,
    )
    widget._root = root
    return widget, button, flyout


def _focus(button, event_type: QEvent.Type, reason=Qt.FocusReason.MouseFocusReason) -> None:
    QApplication.instance().notify(button, QFocusEvent(event_type, reason))


def _visibility_stand(monkeypatch):
    """One live installation exactly like the app builds it on hover."""
    monkeypatch.setattr(tm, "_query_overlay", lambda _store, _cap, default=None: default)
    widget, button, flyout = _make_visibility_widget()
    window = _WindowStub()
    host = _Host(window)
    manager = _transient_manager(monkeypatch, host)
    controller = tm.MagnifierVisibilityController(manager, widget)
    host.controller = controller
    manager._services["panel_visibility"] = controller
    ui_manager = _UIManagerStub(manager)
    close_window = SimpleNamespace(
        _closing=False,
        app_context=None,
        presenter=SimpleNamespace(ui_manager=ui_manager),
    )
    return SimpleNamespace(
        widget=widget,
        button=button,
        flyout=flyout,
        host=host,
        manager=manager,
        controller=controller,
        window=window,
        close_window=close_window,
    )


# --------------------------------------------------------------------------
# the live controller still reacts while the app runs (no over-latching)
# --------------------------------------------------------------------------


def test_running_controller_still_hides_on_focus_out(qapp, monkeypatch):
    stand = _visibility_stand(monkeypatch)

    _focus(stand.button, QEvent.Type.FocusOut)

    assert stand.flyout.hide_calls == 1, (
        "an un-latched controller stopped reacting to FocusOut — the latch "
        "must only engage on shutdown"
    )


# --------------------------------------------------------------------------
# the close step latches the transients off
# --------------------------------------------------------------------------


def test_close_step_stops_the_focus_out_reaction(qapp, monkeypatch):
    """The window shutdown pipeline's first step must silence the controller.

    Reproduces the owner's loop: a FocusOut that arrives after the window is
    closing still ran ``hide()`` (and, on the FocusIn leg, re-armed the hover
    timer that re-opens the flyout).
    """
    stand = _visibility_stand(monkeypatch)

    MarkShuttingDownStep().run(stand.close_window)

    assert stand.close_window._closing is True

    hidden_before = stand.flyout.hide_calls
    scheduled_before = list(stand.flyout.scheduled)

    _focus(stand.button, QEvent.Type.FocusOut)

    assert stand.flyout.hide_calls == hidden_before, (
        "a FocusOut delivered after the close step still called hide() — the "
        "post-close [magnifier-visibility] event=9 loop"
    )
    assert stand.flyout.scheduled == scheduled_before, (
        "a FocusOut delivered after the close step still armed the flyout "
        "auto-hide timer"
    )


def test_close_step_removes_the_filter_and_the_hover_timer(qapp, monkeypatch):
    stand = _visibility_stand(monkeypatch)
    stand.controller._hover_timer.start(150)
    assert stand.controller._hover_timer.is_active() is True

    MarkShuttingDownStep().run(stand.close_window)

    wiring = getattr(stand.widget, tm._WIRING_ATTR, {})
    assert "visibility" not in wiring, (
        "the close step left the event filter installed on btn_magnifier"
    )
    assert stand.controller._hover_timer.is_active() is False, (
        "the close step left the hover timer armed — it re-opens the flyout"
    )
    assert stand.manager._services == {}, (
        "the transient manager still caches services after shutdown"
    )

    _focus(stand.button, QEvent.Type.FocusOut)
    assert stand.host.deliveries == 0, (
        "the removed filter still received the button's focus event"
    )


def test_host_window_closing_flag_alone_latches(qapp, monkeypatch):
    """The window's own ``_closing`` flag is the second latch input: a
    controller built (or still live) after the pipeline already ran must be
    inert as well."""
    stand = _visibility_stand(monkeypatch)
    stand.window._closing = True

    _focus(stand.button, QEvent.Type.FocusOut)

    assert stand.flyout.hide_calls == 0


def test_instances_controller_is_latched_too(qapp, monkeypatch):
    monkeypatch.setattr(tmi, "AnchoredPopupBubbleController", _BubbleStub)
    _BubbleStub.instances = []
    root = QWidget()
    button = _Counter(root)
    widget = SimpleNamespace(btn_magnifier_instances=button)
    window = _WindowStub()
    host = _Host(window)
    host._magn_instances_popup_open = True
    manager = _transient_manager(monkeypatch, host)
    controller = tmi.MagnifierInstancesPopupController(manager, widget)
    host.controller = controller
    manager._services["panel_instances"] = controller

    MarkShuttingDownStep().run(
        SimpleNamespace(
            _closing=False,
            app_context=None,
            presenter=SimpleNamespace(ui_manager=_UIManagerStub(manager)),
        )
    )

    restarts = sum(bubble.restart_calls for bubble in _BubbleStub.instances)
    _focus(button, QEvent.Type.FocusOut)
    assert sum(bubble.restart_calls for bubble in _BubbleStub.instances) == restarts, (
        "the instances popup still restarted its auto-hide timer after close"
    )
    assert getattr(widget, tm._WIRING_ATTR, {}) == {}


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


# --------------------------------------------------------------------------
# the close path itself: quit once, pipeline once
# --------------------------------------------------------------------------


def test_close_path_requests_quit_once_and_runs_the_pipeline_once(qapp, monkeypatch):
    """Re-entrant closes must not re-run the shutdown pipeline.

    The frame-less CSD close button stays clickable while the pipeline runs
    (and the magnifier popup used to re-open over it), so a second close in
    the same turn is reachable; it must only re-assert the quit, never run
    every shutdown step again.
    """
    import ui.main_window.window as window_module

    quit_requests: list[object] = []
    monkeypatch.setattr(
        window_module,
        "_request_app_quit",
        lambda app: quit_requests.append(app),
        raising=False,
    )
    deferred: list[int] = []

    class _QTimerSpy:
        @staticmethod
        def singleShot(ms, fn) -> None:  # noqa: N802 - Qt name
            # Pre-fix shape: the quit was deferred to a 0-timer. Recorded, not
            # fired, so a RED run cannot poison the session's QApplication.
            deferred.append(ms)

    monkeypatch.setattr(window_module, "QTimer", _QTimerSpy)

    pipeline_runs: list[object] = []

    class _PipelineSpy:
        def run(self, window) -> None:
            pipeline_runs.append(window)

    class _StubMainWindow(window_module.MainWindow):
        def __init__(self) -> None:
            QWidget.__init__(self)
            self._shutdown_pipeline = _PipelineSpy()

    window = _StubMainWindow()
    window.close()
    window.close()

    assert len(pipeline_runs) == 1, (
        f"the shutdown pipeline ran {len(pipeline_runs)} times for two close "
        "requests"
    )
    assert len(quit_requests) == 1, (
        f"the close path requested application quit {len(quit_requests)} "
        f"times (deferred 0-timers: {deferred}); it must request it once, in "
        "the same turn"
    )


def test_close_path_quits_even_when_a_shutdown_step_raises(qapp, monkeypatch):
    """The quit is owed even if a shutdown step blows up.

    Pre-fix, ``closeEvent`` ran the pipeline unguarded and asked for the quit
    only *after* every step had returned, so one raising step silently cost
    the hide, the accepted event and the quit: the window stayed up and the
    process stayed in ``exec()`` — the owner's "the application will not
    close" (2026-10-26).
    """
    import ui.main_window.window as window_module

    quit_requests: list[object] = []
    monkeypatch.setattr(
        window_module,
        "_request_app_quit",
        lambda app: quit_requests.append(app),
        raising=False,
    )

    class _RaisingPipeline:
        def run(self, window) -> None:
            raise RuntimeError("a shutdown step raised (stand)")

    class _StubMainWindow(window_module.MainWindow):
        def __init__(self) -> None:
            QWidget.__init__(self)
            self._shutdown_pipeline = _RaisingPipeline()
            self.hide_calls = 0

        def hide(self) -> None:  # noqa: N802 - Qt name
            self.hide_calls += 1
            super().hide()

    window = _StubMainWindow()
    window.close()

    assert quit_requests, (
        "a raising shutdown step swallowed the quit — the process would stay "
        "in QApplication.exec()"
    )
    assert window.hide_calls >= 1, (
        "a raising shutdown step skipped the hide — the window stays on screen"
    )
