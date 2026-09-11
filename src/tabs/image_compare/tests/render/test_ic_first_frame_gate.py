"""Image Compare first-frame signals require completed QRhi presents."""

from __future__ import annotations

from types import SimpleNamespace

from PySide6.QtGui import QColor


def test_render_clear_frame_propagates_renderer_bool(monkeypatch):
    from ui.canvas_infra.rhi import rhi_render

    monkeypatch.setattr(rhi_render, "resolve_clear_color", lambda _w: object())

    class _Renderer:
        def render(self, widget, command_buffer, clear_color):
            assert clear_color is not None
            return False

    widget = SimpleNamespace(_rhi_renderer=_Renderer())
    assert rhi_render.render_clear_frame(widget, object()) is False


def test_resolve_clear_color_forces_opaque_for_live_canvas():
    from ui.canvas_infra.rhi.rhi_render import resolve_clear_color

    widget = SimpleNamespace(
        _use_plan_fill_clear=False,
        _theme_background_color=QColor(10, 20, 30, 0),
        _active_render_plan=None,
    )
    color = resolve_clear_color(widget)
    assert color.alpha() == 255
    assert (color.red(), color.green(), color.blue()) == (10, 20, 30)


def test_resolve_clear_color_opaque_for_export_warmup_without_plan():
    """GPU-export warm-up canvas (no plan yet) must not clear transparently —
    a shown offscreen widget would read as a see-through hole."""
    from ui.canvas_infra.rhi.rhi_render import resolve_clear_color

    widget = SimpleNamespace(
        _use_plan_fill_clear=True,
        _active_render_plan=None,
        _theme_background_color=QColor(10, 20, 30, 0),
    )
    color = resolve_clear_color(widget)
    assert color.alpha() == 255
    assert (color.red(), color.green(), color.blue()) == (10, 20, 30)


def test_resolve_clear_color_stays_transparent_for_export_plan_without_fill():
    """A real export plan without fill keeps transparent pad pixels."""
    from ui.canvas_infra.rhi.rhi_render import resolve_clear_color

    widget = SimpleNamespace(
        _use_plan_fill_clear=True,
        _active_render_plan=SimpleNamespace(fill_rgba=None),
        _theme_background_color=QColor(10, 20, 30, 0),
    )
    color = resolve_clear_color(widget)
    assert color.alpha() == 0


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


def test_ic_render_emits_after_settle_flush(monkeypatch):
    """firstFrameRendered is emitted only after the settle flush makes the
    frame compositor-visible — mirroring multi_compare (on Wayland/Vulkan the
    present is recorded while the compositor still shows the untouched
    transparent subsurface, and only flush_qrhi_compositor restacks it)."""
    from tabs.image_compare.canvas import widget as widget_mod

    scheduled: list[object] = []
    monkeypatch.setattr(widget_mod, "_first_visual_present_count", lambda: 1)
    monkeypatch.setattr(
        widget_mod.QTimer,
        "singleShot",
        lambda _ms, cb: scheduled.append(cb),
    )
    monkeypatch.setattr(widget_mod, "render_clear_frame", lambda _w, _cb: True)
    monkeypatch.setattr(
        "ui.canvas_infra.rhi.rhi_present_sync.flush_qrhi_compositor",
        lambda *_a, **_k: None,
    )

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

    assert emitted == []  # deferred until the settle flush runs
    assert widget._rhi_presents_completed == 1
    assert scheduled  # settle flush scheduled

    scheduled.pop()()  # run the settle flush -> emit
    assert emitted == ["frame", "visual"]


def test_ic_render_waits_required_presents_before_flush_emit(monkeypatch):
    from tabs.image_compare.canvas import widget as widget_mod

    scheduled: list[object] = []
    monkeypatch.setattr(widget_mod, "_first_visual_present_count", lambda: 2)
    monkeypatch.setattr(
        widget_mod.QTimer,
        "singleShot",
        lambda _ms, cb: scheduled.append(cb),
    )
    monkeypatch.setattr(widget_mod, "render_clear_frame", lambda _w, _cb: True)
    monkeypatch.setattr(
        "ui.canvas_infra.rhi.rhi_present_sync.flush_qrhi_compositor",
        lambda *_a, **_k: None,
    )

    emitted: list[str] = []
    widget = widget_mod.CanvasWidget.__new__(widget_mod.CanvasWidget)
    widget._first_frame_rendered_emitted = False
    widget._rhi_presents_completed = 0
    widget.firstFrameRendered = SimpleNamespace(emit=lambda: emitted.append("frame"))
    widget.firstVisualFrameReady = SimpleNamespace(
        emit=lambda: emitted.append("visual")
    )
    widget._request_update = lambda: None

    # Present #1 -> flush runs, but the required-present gate still holds.
    widget_mod.CanvasWidget.render(widget, object())
    assert widget._rhi_presents_completed == 1
    scheduled.pop()()
    assert emitted == []

    # Present #2 -> flush runs -> gate passes -> emit.
    widget_mod.CanvasWidget.render(widget, object())
    assert widget._rhi_presents_completed == 2
    scheduled.pop()()
    assert emitted == ["frame", "visual"]


def test_ic_settle_flush_skipped_while_drag_visible(monkeypatch):
    """Startup settle must not fire mid-drag (xdg-activation storm).

    Regression (Wayland): ``render()`` schedules ``_settle_first_presents``
    for every present ``<= 10`` — including drag presents, whose counter
    shares the startup sequence. Its activated flush (``raise_`` +
    ``activateWindow``) lands while the drag source owns focus: Mutter
    answers with busy-cursor flashes, plus full repaint churn on the GUI
    thread inside the show→visible window. While the DnD zone is shown the
    DnD settle chain owns restack — the pre-emit gate check still runs.
    """
    from tabs.image_compare.canvas import widget as widget_mod

    scheduled: list[object] = []
    monkeypatch.setattr(widget_mod, "_first_visual_present_count", lambda: 1)
    monkeypatch.setattr(
        widget_mod.QTimer,
        "singleShot",
        lambda _ms, cb: scheduled.append(cb),
    )
    monkeypatch.setattr(widget_mod, "render_clear_frame", lambda _w, _cb: True)
    flushes: list[tuple[tuple[object, ...], dict[str, object]]] = []
    monkeypatch.setattr(
        "ui.canvas_infra.rhi.rhi_present_sync.flush_qrhi_compositor",
        lambda *_a, **_k: flushes.append((_a, _k)),
    )

    emitted: list[str] = []
    widget = widget_mod.CanvasWidget.__new__(widget_mod.CanvasWidget)
    widget._first_frame_rendered_emitted = False
    widget._rhi_presents_completed = 0
    widget._dnd_show_t0 = None
    widget._dnd_first_present_t = None
    widget.runtime_state = SimpleNamespace(_drag_overlay_visible=True)
    widget.firstFrameRendered = SimpleNamespace(emit=lambda: emitted.append("frame"))
    widget.firstVisualFrameReady = SimpleNamespace(
        emit=lambda: emitted.append("visual")
    )
    widget._request_update = lambda: None

    widget_mod.CanvasWidget.render(widget, object())
    assert widget._rhi_presents_completed == 1
    assert scheduled  # settle still scheduled (emit gate must run)

    scheduled.pop()()  # run the settle flush -> skipped, emit proceeds
    assert flushes == []
    assert emitted == ["frame", "visual"]