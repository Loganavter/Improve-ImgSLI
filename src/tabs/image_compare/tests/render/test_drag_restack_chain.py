"""DnD settle kick: single delayed restack, drag-scoped.

The delayed kick lands amid presented tile-frames (the immediate
show-edge flush restacks while only the pre-tile buffer exists).
Single-shot with no re-arm: repeated-kick experiments moved nothing
visually (whole-window stall during grabs lives outside our timing),
so this stays the minimal recipe. Every kick is activation-free (no
raise_/activateWindow during an external drag — guaranteed-denied
xdg-activation, Mutter «ожидает» banner).
"""

from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _widget(visible=True):
    state = SimpleNamespace(_drag_overlay_visible=bool(visible))
    return SimpleNamespace(runtime_state=state), state


def test_restack_kick_fires_while_visible(monkeypatch):
    from tabs.image_compare.canvas import widget as wmod
    from ui.canvas_infra.rhi import rhi_present_sync as sync

    calls: list[tuple[str, bool]] = []
    monkeypatch.setattr(
        sync,
        "flush_qrhi_compositor",
        lambda w, *, reason="", activate=True, chrome=True: calls.append(
            (reason, activate)
        ),
    )
    scheduled: list[tuple[int, object]] = []
    import PySide6.QtCore as core

    monkeypatch.setattr(
        core.QTimer, "singleShot", staticmethod(lambda ms, fn: scheduled.append((ms, fn)))
    )

    w, _state = _widget(visible=True)
    wmod._schedule_drag_restack(w)
    assert [ms for ms, _ in scheduled] == [wmod._DND_RESTACK_DELAY_MS]

    _ms, kick = scheduled.pop(0)
    kick()
    assert calls == [("ic-dnd-show-settle", False)]
    assert scheduled == []  # single-shot, no re-arm


def test_restack_kick_stands_down_when_hidden(monkeypatch):
    from tabs.image_compare.canvas import widget as wmod
    from ui.canvas_infra.rhi import rhi_present_sync as sync

    calls: list[tuple[str, bool]] = []
    monkeypatch.setattr(
        sync,
        "flush_qrhi_compositor",
        lambda w, *, reason="", activate=True, chrome=True: calls.append(
            (reason, activate)
        ),
    )
    scheduled: list[tuple[int, object]] = []
    import PySide6.QtCore as core

    monkeypatch.setattr(
        core.QTimer, "singleShot", staticmethod(lambda ms, fn: scheduled.append((ms, fn)))
    )

    w, state = _widget(visible=True)
    wmod._schedule_drag_restack(w)
    # Drag ends before the kick fires: no flush.
    state._drag_overlay_visible = False
    _ms, kick = scheduled.pop(0)
    kick()
    assert calls == []
