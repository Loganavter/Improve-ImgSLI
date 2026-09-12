"""Idle pipeline primer keep-warm ticker (DnD feedback latency).

A long-static canvas shows drop feedback ~350 ms late; silent periodic
RHI frames keep it primed so the first drag frame displays immediately.
Guards: opt-out via IMGSLI_DND_KEEPWARM_MS=0, single start, drag pump
owns frames while the zone is shown (tested via visibility/minimized
short-circuits only where reachable without an event loop).
"""

from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _fake_canvas():
    from PySide6.QtCore import QObject

    from tabs.image_compare.canvas import widget as wmod

    class Fake(QObject):
        def __init__(self):
            super().__init__()
            self.runtime_state = SimpleNamespace(_drag_overlay_visible=False)
            self.updates = 0
            self._visible = True
            self._minimized = False

        def isVisible(self):  # noqa: N802
            return self._visible

        def window(self):
            return SimpleNamespace(isMinimized=lambda: self._minimized)

        def update(self):  # noqa: N802
            self.updates += 1

    return Fake(), wmod


def _timers_of(fake):
    from PySide6.QtCore import QTimer

    return [t for t in fake.findChildren(QTimer) if t.interval() > 0]


def test_keepwarm_starts_ticker_by_default(qapp, monkeypatch):
    fake, wmod = _fake_canvas()
    monkeypatch.delenv("IMGSLI_DND_KEEPWARM_MS", raising=False)
    wmod.CanvasWidget._ensure_dnd_keepwarm(fake)
    assert getattr(fake, "_dnd_keepwarm_started", False) is True
    timers = _timers_of(fake)
    assert len(timers) == 1
    assert timers[0].interval() == 250
    assert timers[0].isActive()
    # Second call must not double-start.
    wmod.CanvasWidget._ensure_dnd_keepwarm(fake)
    assert len(_timers_of(fake)) == 1


def test_keepwarm_opt_out(qapp, monkeypatch):
    fake, wmod = _fake_canvas()
    monkeypatch.setenv("IMGSLI_DND_KEEPWARM_MS", "0")
    wmod.CanvasWidget._ensure_dnd_keepwarm(fake)
    assert getattr(fake, "_dnd_keepwarm_started", False) is False
    assert _timers_of(fake) == []


def test_keepwarm_custom_interval(qapp, monkeypatch):
    fake, wmod = _fake_canvas()
    monkeypatch.setenv("IMGSLI_DND_KEEPWARM_MS", "500")
    wmod.CanvasWidget._ensure_dnd_keepwarm(fake)
    timers = _timers_of(fake)
    assert len(timers) == 1
    assert timers[0].interval() == 500
