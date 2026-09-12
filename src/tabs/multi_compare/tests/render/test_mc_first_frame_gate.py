"""Multi Compare first-frame signal requires completed QRhi presents.

Mirrors image_compare's test_ic_first_frame_gate.py -- both canvases now
share the same settle-present contract (see canvas_widget.py's module-level
comment on _FIRST_PRESENT_SETTLE_COUNT).

Multi Compare additionally emits *after* the compositor settle flush, not
on the present itself (see canvas_widget.render's docstring): on
Wayland/Vulkan the first beginPass/endPass is recorded while the compositor
still shows the untouched transparent subsurface, so firstFrameRendered is
only trusted once flush_qrhi_compositor() has run.
"""

from __future__ import annotations

from types import SimpleNamespace


def _make_widget(painted: bool):
    from tabs.multi_compare.ui import canvas_widget as widget_mod

    widget = widget_mod.MultiCompareCanvasWidget.__new__(
        widget_mod.MultiCompareCanvasWidget
    )
    widget._first_frame_emitted = False
    widget._rhi_presents_completed = 0
    widget._renderer = SimpleNamespace(render=lambda _cb: painted)
    emitted: list[str] = []
    widget.firstFrameRendered = SimpleNamespace(emit=lambda: emitted.append("frame"))
    return widget_mod, widget, emitted


def _noop_flush(monkeypatch):
    from ui.canvas_infra.rhi import rhi_present_sync

    monkeypatch.setattr(
        rhi_present_sync, "flush_qrhi_compositor", lambda *a, **k: None
    )


def test_mc_render_skips_signal_when_pass_not_recorded():
    widget_mod, widget, emitted = _make_widget(painted=False)

    widget_mod.MultiCompareCanvasWidget.render(widget, object())

    assert emitted == []
    assert widget._first_frame_emitted is False
    assert widget._rhi_presents_completed == 0


def test_mc_render_emits_after_flush_on_linux(monkeypatch):
    from tabs.multi_compare.ui import canvas_widget as widget_mod

    scheduled: list[object] = []
    monkeypatch.setattr(widget_mod, "_first_visual_present_count", lambda: 1)
    monkeypatch.setattr(
        widget_mod.QTimer, "singleShot", lambda _ms, cb: scheduled.append(cb)
    )
    _noop_flush(monkeypatch)

    widget_mod, widget, emitted = _make_widget(painted=True)

    widget_mod.MultiCompareCanvasWidget.render(widget, object())

    # Not emitted on the present itself — only once the settle flush ran.
    assert emitted == []
    assert widget._rhi_presents_completed == 1
    assert scheduled  # settle flush scheduled

    for cb in scheduled:
        cb()
    assert emitted == ["frame"]
    assert widget._first_frame_emitted is True


def test_mc_render_waits_second_present_on_windows(monkeypatch):
    from tabs.multi_compare.ui import canvas_widget as widget_mod

    scheduled: list[object] = []
    monkeypatch.setattr(widget_mod, "_first_visual_present_count", lambda: 2)
    monkeypatch.setattr(
        widget_mod.QTimer, "singleShot", lambda _ms, cb: scheduled.append(cb)
    )
    _noop_flush(monkeypatch)

    widget_mod, widget, emitted = _make_widget(painted=True)

    widget_mod.MultiCompareCanvasWidget.render(widget, object())
    assert emitted == []
    assert widget._rhi_presents_completed == 1

    for cb in scheduled:
        cb()
    assert emitted == []  # still one present short

    widget_mod.MultiCompareCanvasWidget.render(widget, object())
    assert emitted == []
    assert widget._rhi_presents_completed == 2

    for cb in scheduled:
        cb()
    assert emitted == ["frame"]


def test_mc_default_visual_gate_is_four_presents():
    """The default gate must wait for the first frame that actually reaches
    the display (empirically present #4 on Wayland/Vulkan), and the settle
    kick must keep running until that point or the emit never fires."""
    from tabs.multi_compare.ui import canvas_widget as widget_mod

    gate = widget_mod._first_visual_present_count()
    assert gate >= 4
    assert widget_mod._FIRST_PRESENT_SETTLE_COUNT >= gate


def test_mc_settle_pump_collapses_intermediate_flushes(monkeypatch):
    """A4/P4 settle-pump collapse: only the boundary presents (1st + 10th)
    pay the full compositor restack; intermediates pump a single canvas
    repaint. Count invariant (every painted present counts) and the
    ``presents >= 10`` emit gate stay untouched."""
    from tabs.multi_compare.ui import canvas_widget as widget_mod
    from ui.canvas_infra.rhi import rhi_present_sync

    flushes: list[str] = []
    scheduled: list[object] = []
    monkeypatch.setattr(widget_mod, "_first_visual_present_count", lambda: 10)
    monkeypatch.setattr(
        rhi_present_sync, "flush_qrhi_compositor", lambda *a, **k: flushes.append("flush")
    )
    monkeypatch.setattr(
        widget_mod.QTimer, "singleShot", lambda _ms, cb: scheduled.append(cb)
    )

    widget_mod, widget, emitted = _make_widget(painted=True)

    for _ in range(3):
        widget_mod.MultiCompareCanvasWidget.render(widget, object())
    assert widget._rhi_presents_completed == 3
    assert len(scheduled) == 1  # only present #1 restacks
    assert emitted == []

    for _ in range(6):
        widget_mod.MultiCompareCanvasWidget.render(widget, object())
    assert widget._rhi_presents_completed == 9
    assert len(scheduled) == 1  # intermediates pump via update(), no flush

    widget_mod.MultiCompareCanvasWidget.render(widget, object())
    assert widget._rhi_presents_completed == 10
    assert len(scheduled) == 2  # tenth present restacks pre-emit

    for cb in scheduled:
        cb()
    assert emitted == ["frame"]
    assert widget._first_frame_emitted is True