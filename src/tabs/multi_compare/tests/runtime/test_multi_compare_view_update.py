"""QRhi view updates must not rely on a geometry change to flush zoom/pan."""

from __future__ import annotations

from types import SimpleNamespace

from PySide6.QtCore import QTimer

from tabs.multi_compare.models import MultiCompareState
from tabs.multi_compare.ui.canvas_widget import MultiCompareCanvasWidget


def test_set_state_schedules_deferred_view_update(qapp, monkeypatch):
    canvas = MultiCompareCanvasWidget()
    updates: list[str] = []
    monkeypatch.setattr(canvas, "update", lambda: updates.append("update"))
    monkeypatch.setattr(canvas, "_sync_textures", lambda: None)
    monkeypatch.setattr(canvas, "_rebuild_composition", lambda: None)

    deferred: list = []

    def capture_single_shot(ms, callback):
        deferred.append(callback)
        return None

    monkeypatch.setattr(QTimer, "singleShot", staticmethod(capture_single_shot))

    canvas.set_state(MultiCompareState())
    assert updates[0] == "update"
    assert canvas._view_update_pending is True
    assert len(deferred) == 1

    before = len(updates)
    canvas.setVisible(True)
    deferred[0]()
    assert canvas._view_update_pending is False
    assert len(updates) > before
    canvas.deleteLater()


def test_request_view_update_coalesces_pending_timer(qapp, monkeypatch):
    canvas = MultiCompareCanvasWidget()
    monkeypatch.setattr(canvas, "update", lambda: None)
    shots: list[int] = []
    monkeypatch.setattr(
        QTimer, "singleShot", staticmethod(lambda _ms, _cb: shots.append(1))
    )

    canvas.request_view_update()
    canvas.request_view_update()
    assert shots == [1]
    canvas.deleteLater()


def test_store_change_re_requests_update_after_zoom_indicator(qapp, monkeypatch):
    """Reset-from-overlay: indicator hide must not leave a stale RHI frame."""
    from tabs.multi_compare.widget import MultiCompareWidget
    from tabs.multi_compare.scene import actions

    widget = MultiCompareWidget.__new__(MultiCompareWidget)
    widget._font_popup_open = False
    calls: list[str] = []

    canvas = SimpleNamespace(
        set_state=lambda _s: calls.append("set_state"),
        request_view_update=lambda: calls.append("request_view_update"),
    )
    widget.canvas = canvas
    widget._sync_zoom_indicator = lambda: calls.append("sync_indicator")
    widget.sync_divider_toolbar = lambda: None
    widget._sync_font_settings_flyout = lambda: None

    MultiCompareWidget._on_store_change(
        widget, actions.reset_view(), MultiCompareState()
    )
    assert calls == ["set_state", "sync_indicator", "request_view_update"]
