"""DnD overlay frame pump: frames must flow while the zone is visible.

Regression (Wayland): with the overlay SSOT True but no steady update
source, the canvas can present zero frames during an external drag — the
compositor keeps showing the pre-drag subsurface buffer and the tiles never
appear. (Found because the first-frame sampler's 50 ms grabs accidentally
acted as the pump: with ``IMGSLI_IC_FIRST_FRAME_DEBUG=1`` tiles rendered,
without it nothing did.) The handler must therefore pump canvas updates on
a ~20fps drag-scoped timer from show to hide.
"""

from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _handler(qtbot):
    from events.window_event_handler import WindowEventHandler

    updates = []
    state = {"visible": False}

    canvas = SimpleNamespace(
        update=lambda: updates.append(1),
        windowHandle=lambda: None,
    )
    widget = SimpleNamespace(
        image_label=canvas,
        update_drag_overlays=lambda horizontal, visible=False: state.update(
            visible=bool(visible)
        ),
        is_drag_overlay_visible=lambda: state["visible"],
    )
    store = SimpleNamespace(
        viewport=SimpleNamespace(view_state=SimpleNamespace(is_horizontal=False))
    )
    handler = WindowEventHandler(store, None, widget, parent=None)
    return handler, updates


def _enter_event():
    mime = SimpleNamespace(hasUrls=lambda: True)
    return SimpleNamespace(
        mimeData=lambda: mime,
        setDropAction=lambda action: None,
        accept=lambda: None,
    )


def test_frame_pump_runs_while_overlay_visible(qtbot):
    handler, updates = _handler(qtbot)
    assert not handler._drag_pump_timer.isActive()

    handler.handle_drag_enter(_enter_event())
    assert handler._drag_pump_timer.isActive()

    handler._pump_drag_frame()
    handler._pump_drag_frame()
    assert len(updates) == 2

    handler._handle_deferred_drag_leave()
    assert not handler._drag_pump_timer.isActive()


def test_frame_pump_self_stops_when_overlay_gone(qtbot):
    handler, updates = _handler(qtbot)
    handler.handle_drag_enter(_enter_event())
    assert handler._drag_pump_timer.isActive()

    # Overlay hidden by other means (e.g. drop path): next tick stops itself.
    handler.widget.update_drag_overlays(False, visible=False)
    handler._pump_drag_frame()
    assert not handler._drag_pump_timer.isActive()
    assert updates == []


def test_title_probe_marks_enter_and_restores_on_leave(qtbot, monkeypatch):
    from types import SimpleNamespace as _NS

    monkeypatch.setenv("IMGSLI_DND_TITLE_PROBE", "1")
    handler, _updates = _handler(qtbot)
    titles: list[str] = []
    win = _NS(
        windowTitle=lambda: "Improve ImgSLI",
        setWindowTitle=lambda t: titles.append(t),
    )
    handler.widget = _NS(
        image_label=handler.widget.image_label,
        update_drag_overlays=handler.widget.update_drag_overlays,
        is_drag_overlay_visible=handler.widget.is_drag_overlay_visible,
        window=lambda: win,
    )

    handler.handle_drag_enter(_enter_event())
    assert titles == ["◉ DND-ENTER"]

    handler._handle_deferred_drag_leave()
    assert titles == ["◉ DND-ENTER", "Improve ImgSLI"]
