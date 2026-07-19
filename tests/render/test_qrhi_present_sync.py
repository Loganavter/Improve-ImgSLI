"""Debounced Wayland/Vulkan compositor sync after MC view changes."""

from __future__ import annotations

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QWidget

from ui.widgets.canvas import rhi_present_sync as sync


@pytest.fixture
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_schedule_compositor_sync_debounces(qapp, monkeypatch):
    widget = QWidget()
    calls: list[str] = []

    monkeypatch.setattr(
        sync,
        "flush_qrhi_compositor",
        lambda w, *, reason="": calls.append(reason),
    )
    monkeypatch.setattr(sync, "_DEBOUNCE_MS", 30)

    sync.schedule_compositor_sync(widget, reason="a")
    sync.schedule_compositor_sync(widget, reason="b")
    timer = getattr(widget, sync._TIMER_ATTR)
    assert isinstance(timer, QTimer)
    assert timer.isActive()

    # Advance past debounce without relying on real wall-clock in CI.
    timer.stop()
    timer.timeout.emit()

    assert calls == ["b"]
    widget.close()


def test_ensure_window_active_noop_when_already_active(qapp, monkeypatch):
    widget = QWidget()
    widget.show()
    monkeypatch.setattr(
        qapp,
        "applicationState",
        lambda: __import__("PySide6.QtCore", fromlist=["Qt"]).Qt.ApplicationState.ApplicationActive,
    )
    assert sync.ensure_window_active_for_qrhi(widget) is False
    widget.close()
