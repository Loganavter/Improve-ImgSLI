"""Image Compare first-frame signals require a completed QRhi pass."""

from __future__ import annotations

from types import SimpleNamespace


def test_render_clear_frame_propagates_renderer_bool(monkeypatch):
    from ui.widgets.canvas import rhi_render

    monkeypatch.setattr(rhi_render, "resolve_clear_color", lambda _w: object())

    class _Renderer:
        def render(self, widget, command_buffer, clear_color):
            assert clear_color is not None
            return False

    widget = SimpleNamespace(_rhi_renderer=_Renderer())
    assert rhi_render.render_clear_frame(widget, object()) is False


def test_ic_render_skips_signals_when_pass_not_recorded(monkeypatch):
    from tabs.image_compare.canvas import widget as widget_mod

    monkeypatch.setattr(widget_mod, "render_clear_frame", lambda _w, _cb: False)

    emitted: list[str] = []
    widget = widget_mod.CanvasWidget.__new__(widget_mod.CanvasWidget)
    widget._first_frame_rendered_emitted = False
    widget.firstFrameRendered = SimpleNamespace(emit=lambda: emitted.append("frame"))
    widget.firstVisualFrameReady = SimpleNamespace(
        emit=lambda: emitted.append("visual")
    )
    widget._request_update = lambda: emitted.append("update")

    widget_mod.CanvasWidget.render(widget, object())

    assert emitted == []
    assert widget._first_frame_rendered_emitted is False


def test_ic_render_emits_and_schedules_next_tick(monkeypatch):
    from tabs.image_compare.canvas import widget as widget_mod

    scheduled: list[object] = []
    monkeypatch.setattr(
        widget_mod.QTimer,
        "singleShot",
        lambda _ms, cb: scheduled.append(cb),
    )
    monkeypatch.setattr(widget_mod, "render_clear_frame", lambda _w, _cb: True)

    emitted: list[str] = []
    widget = widget_mod.CanvasWidget.__new__(widget_mod.CanvasWidget)
    widget._first_frame_rendered_emitted = False
    widget.firstFrameRendered = SimpleNamespace(emit=lambda: emitted.append("frame"))
    widget.firstVisualFrameReady = SimpleNamespace(
        emit=lambda: emitted.append("visual")
    )
    widget._request_update = lambda: emitted.append("update")

    widget_mod.CanvasWidget.render(widget, object())

    assert emitted == ["frame", "visual"]
    assert widget._first_frame_rendered_emitted is True
    assert scheduled == [widget._request_update]
