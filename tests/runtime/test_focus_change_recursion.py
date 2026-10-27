"""One focus/close sweep per *process* — not one per manager instance.

Live crash (2026-10-27), caught in the owner's running window::

    RecursionError: maximum recursion depth exceeded
      ui_manager.py:197          _on_app_focus_changed -> transient.on_app_focus_changed
      transient_ui_manager.py:249 -> closing.on_app_focus_changed
      closing.py:187             transient_close_debug(...)
      host_debug.py:65           _emit -> _env_flag -> debug_flags.py:70 env_flag
      debug_flags.py:59          env_value -> os.environ.get -> RecursionError

The env lookup is only where the ~1000-frame stack ran out; it is not the
cause. The per-instance ``_in_focus_changed`` latch (c57133a49) bounds a
*single* manager re-entering *itself* — and therefore cannot bound the routes
that re-enter the sweep on a different participant:

* a second ``UIManager`` (its latch is still free while the first is busy),
* a manager resolved lazily *during* the sweep (one latch per tab),
* a nested event pump — ``processEvents()`` / ``activateWindow()`` inside a
  hide path — delivering the deferred ``QTimer.singleShot(0, _run)`` close
  sweep again while the first sweep is still on the stack.

The tests emulate ``QApplication.focusChanged`` synchronously (a Qt signal
runs every slot before ``emit`` returns), so the nesting shape matches
production without needing a window. On 67cfd3015 a second manager joins a
sweep that is still running, and the lazily-built manager / nested close
sweep both recurse to ``RecursionError``.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace

from PySide6.QtWidgets import QApplication

from ui.managers.transient_ui_parts.closing import (
    PopupClosingController,
    begin_transient_sweep,
    end_transient_sweep,
    transient_sweep_depth,
)
from ui.managers.ui_manager import UIManager


class _FocusSignal:
    """Synchronous stand-in for ``QApplication.focusChanged``."""

    def __init__(self) -> None:
        self._slots: list = []

    def connect(self, slot) -> None:
        self._slots.append(slot)

    def emit(self, old=None, new=None) -> None:
        for slot in tuple(self._slots):
            slot(old, new)


def _manager(signal: _FocusSignal, transient_slot) -> UIManager:
    """A UIManager with only the focus path wired (no QObject __init__)."""
    manager = UIManager.__new__(UIManager)
    manager.transient = SimpleNamespace(on_app_focus_changed=transient_slot)
    signal.connect(manager._on_app_focus_changed)
    return manager


def _closing_controller(runs: list) -> PopupClosingController:
    """A PopupClosingController wired to a recording tab extension."""
    controller = PopupClosingController.__new__(PopupClosingController)
    host = SimpleNamespace(
        _is_modal_active=False,
        _interp_popup_open=False,
        _font_popup_open=False,
        font_settings_flyout=None,
        parent_widget=None,
        _active_session_type=None,
    )
    controller.manager = SimpleNamespace(
        host=host,
        _services={},
        interpolation=None,
        font_settings=None,
    )
    controller._tab_extension = SimpleNamespace(hide_same_window=lambda: runs.append(1))
    return controller


def _suppressed_records(caplog) -> list:
    return [
        record
        for record in caplog.records
        if "suppressed re-entrant" in record.getMessage()
    ]


def test_no_sweep_starts_while_another_is_on_the_stack(caplog):
    """Depth limit is one sweep per process, not one per instance latch."""
    signal = _FocusSignal()
    active = 0
    processed: list[str] = []
    nested: list[str] = []

    def _first(old, new):
        nonlocal active
        if active:
            nested.append("first")
        active += 1
        try:
            processed.append("first")
            # A hide()/activateWindow() in the reaction moves focus, which
            # emits focusChanged synchronously before this call returns.
            signal.emit("next", None)
        finally:
            active -= 1

    def _second(old, new):
        nonlocal active
        if active:
            # Reached only if this manager started a sweep of its own while
            # the first manager's sweep was still on the stack.
            nested.append("second")
        active += 1
        try:
            processed.append("second")
        finally:
            active -= 1

    _manager(signal, _first)
    _manager(signal, _second)

    with caplog.at_level(logging.WARNING):
        signal.emit("start", None)

    assert nested == [], (
        "a focus change may not start a second sweep while one is already "
        f"running in this process; nested entries: {nested}"
    )
    assert transient_sweep_depth() == 0
    assert len(_suppressed_records(caplog)) == 1, (
        "a suppressed re-entry must leave exactly one log line, not one per "
        "re-entered frame"
    )


def test_a_manager_created_during_the_sweep_cannot_grow_the_stack(caplog):
    """The "own latch per tab" hole: a manager built *inside* the sweep."""
    signal = _FocusSignal()
    processed: list[int] = []

    def _spawn() -> UIManager:
        manager = UIManager.__new__(UIManager)

        def _on(old, new):
            # A lazily resolved manager has a free latch, so it starts the
            # next sweep and the stack grows one manager per level.
            processed.append(len(processed))
            _spawn()
            signal.emit("next", None)

        manager.transient = SimpleNamespace(on_app_focus_changed=_on)
        signal.connect(manager._on_app_focus_changed)
        return manager

    with caplog.at_level(logging.WARNING):
        _spawn()
        try:
            signal.emit("start", None)
        except RecursionError:
            pass  # the live symptom on 67cfd3015

    assert len(processed) == 1, f"{len(processed)} managers joined one focus change"
    assert transient_sweep_depth() == 0
    assert len(_suppressed_records(caplog)) == 1


def test_nested_close_sweep_from_a_pumped_event_loop_runs_once(caplog):
    """A nested pump delivering the deferred close sweep must not nest it."""
    runs: list[int] = []
    controller = _closing_controller(runs)

    def _hide_same_window():
        runs.append(len(runs) + 1)
        if len(runs) < 500:
            # processEvents()/activateWindow() inside the hide path delivers
            # QTimer.singleShot(0, _run) again while this sweep is on the stack.
            assert controller._hide_transient_same_window_ui_now() is False

    controller._tab_extension = SimpleNamespace(hide_same_window=_hide_same_window)

    with caplog.at_level(logging.WARNING):
        try:
            assert controller._hide_transient_same_window_ui_now() is True
        except RecursionError:
            pass  # the live symptom on 67cfd3015

    assert runs == [1], f"the close sweep re-entered itself {len(runs)} times"
    assert transient_sweep_depth() == 0
    assert len(_suppressed_records(caplog)) == 1


def test_a_close_requested_during_a_sweep_is_deferred_not_dropped(qtbot):
    """A sweep that collides with a running one is re-queued, never nested."""
    runs: list[int] = []
    controller = _closing_controller(runs)

    assert begin_transient_sweep("test-holder")
    try:
        controller.hide_transient_same_window_ui(reason="while_sweep_runs")
        QApplication.processEvents()
        assert runs == [], "the hide must not run inside the running sweep"
    finally:
        end_transient_sweep()

    qtbot.waitUntil(lambda: runs == [1], timeout=2000)
    assert transient_sweep_depth() == 0


def test_sequential_focus_changes_still_sweep():
    """The guard must not latch on: normal focus switching keeps working."""
    signal = _FocusSignal()
    calls: list[tuple] = []
    _manager(signal, lambda old, new: calls.append((old, new)))

    signal.emit("a", "b")
    signal.emit("c", "d")

    assert calls == [("a", "b"), ("c", "d")]
    assert transient_sweep_depth() == 0


def test_a_failing_sweep_releases_the_process_slot():
    signal = _FocusSignal()

    def _boom(old, new):
        raise RuntimeError("downstream died")

    _manager(signal, _boom)

    signal.emit("a", "b")  # must not propagate into Qt signal machinery
    assert transient_sweep_depth() == 0


def test_recursion_error_downstream_is_contained():
    """A RecursionError must not be re-logged with a traceback on the deep stack."""
    signal = _FocusSignal()

    def _deep(old, new):
        raise RecursionError("maximum recursion depth exceeded")

    _manager(signal, _deep)

    signal.emit("a", "b")
    assert transient_sweep_depth() == 0
