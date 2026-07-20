"""Image Compare first-frame signals require completed QRhi presents."""

from __future__ import annotations

from types import SimpleNamespace

from PySide6.QtGui import QColor


def test_render_clear_frame_propagates_renderer_bool(monkeypatch):
    from ui.widgets.canvas import rhi_render

    monkeypatch.setattr(rhi_render, "resolve_clear_color", lambda _w: object())

    class _Renderer:
        def render(self, widget, command_buffer, clear_color):
            assert clear_color is not None
            return False

    widget = SimpleNamespace(_rhi_renderer=_Renderer())
    assert rhi_render.render_clear_frame(widget, object()) is False


def test_resolve_clear_color_forces_opaque_for_live_canvas():
    from ui.widgets.canvas.rhi_render import resolve_clear_color

    widget = SimpleNamespace(
        _use_plan_fill_clear=False,
        _theme_background_color=QColor(10, 20, 30, 0),
        _active_render_plan=None,
    )
    color = resolve_clear_color(widget)
    assert color.alpha() == 255
    assert (color.red(), color.green(), color.blue()) == (10, 20, 30)


def test_ic_render_skips_signals_when_pass_not_recorded(monkeypatch):
    from tabs.image_compare.canvas import widget as widget_mod

    monkeypatch.setattr(widget_mod, "render_clear_frame", lambda _w, _cb: False)

    emitted: list[str] = []
    widget = widget_mod.CanvasWidget.__new__(widget_mod.CanvasWidget)
    widget._first_frame_rendered_emitted = False
    widget._rhi_presents_completed = 0
    widget.firstFrameRendered = SimpleNamespace(emit=lambda: emitted.append("frame"))
    widget.firstVisualFrameReady = SimpleNamespace(
        emit=lambda: emitted.append("visual")
    )
    widget._request_update = lambda: emitted.append("update")

    widget_mod.CanvasWidget.render(widget, object())

    assert emitted == []
    assert widget._first_frame_rendered_emitted is False


def test_ic_render_emits_after_required_presents_on_linux(monkeypatch):
    from tabs.image_compare.canvas import widget as widget_mod

    scheduled: list[object] = []
    monkeypatch.setattr(widget_mod, "_first_visual_present_count", lambda: 1)
    monkeypatch.setattr(
        widget_mod.QTimer,
        "singleShot",
        lambda _ms, cb: scheduled.append(cb),
    )
    monkeypatch.setattr(widget_mod, "render_clear_frame", lambda _w, _cb: True)

    emitted: list[str] = []
    widget = widget_mod.CanvasWidget.__new__(widget_mod.CanvasWidget)
    widget._first_frame_rendered_emitted = False
    widget._rhi_presents_completed = 0
    widget.firstFrameRendered = SimpleNamespace(emit=lambda: emitted.append("frame"))
    widget.firstVisualFrameReady = SimpleNamespace(
        emit=lambda: emitted.append("visual")
    )
    widget._request_update = lambda: None

    widget_mod.CanvasWidget.render(widget, object())

    assert emitted == ["frame", "visual"]
    assert widget._rhi_presents_completed == 1
    assert scheduled  # settle flush scheduled


def test_ic_render_waits_second_present_on_windows(monkeypatch):
    from tabs.image_compare.canvas import widget as widget_mod

    monkeypatch.setattr(widget_mod, "_first_visual_present_count", lambda: 2)
    monkeypatch.setattr(widget_mod.QTimer, "singleShot", lambda *_a, **_k: None)
    monkeypatch.setattr(widget_mod, "render_clear_frame", lambda _w, _cb: True)

    emitted: list[str] = []
    widget = widget_mod.CanvasWidget.__new__(widget_mod.CanvasWidget)
    widget._first_frame_rendered_emitted = False
    widget._rhi_presents_completed = 0
    widget.firstFrameRendered = SimpleNamespace(emit=lambda: emitted.append("frame"))
    widget.firstVisualFrameReady = SimpleNamespace(
        emit=lambda: emitted.append("visual")
    )
    widget._request_update = lambda: None

    widget_mod.CanvasWidget.render(widget, object())
    assert emitted == []
    assert widget._rhi_presents_completed == 1

    widget_mod.CanvasWidget.render(widget, object())
    assert emitted == ["frame", "visual"]
    assert widget._rhi_presents_completed == 2
