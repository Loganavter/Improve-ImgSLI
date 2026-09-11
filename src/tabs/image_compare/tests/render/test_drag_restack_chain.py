"""DnD settle kicks repeat while the zone stays visible (bounded).

Regression context (Wayland): a single fixed-delay restack can land while
the throttled inactive-drag subsurface still holds the pre-tile buffer —
and then nothing re-kicks the compositor, so the screen stays stale while
presents flow. The chain re-arms while the zone stays visible, bounded so
a stuck True can never spin timers forever, and every kick is
activation-free (no raise_/activateWindow during an external drag —
guaranteed-denied xdg-activation, Mutter «ожидает» banner).
"""

from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _widget(visible=True):
    state = SimpleNamespace(_drag_overlay_visible=bool(visible))
    return SimpleNamespace(runtime_state=state), state


def _drain(scheduled, limit=10):
    fires = 0
    while scheduled and fires < limit:
        _ms, fn = scheduled.pop(0)
        fn()
        fires += 1
    return fires


def _flush_mock(calls):
    def _flush(w, *, reason="", activate=True, chrome=True):
        calls.append((reason, activate, chrome))

    return _flush


def _singleshot_mock(scheduled):
    import PySide6.QtCore as core

    return staticmethod(lambda ms, fn: scheduled.append((ms, fn)))


def test_restack_chain_kicks_bounded_while_visible(monkeypatch):
    from tabs.image_compare.canvas import widget as wmod
    from ui.canvas_infra.rhi import rhi_present_sync as sync

    monkeypatch.delenv("IMGSLI_DND_KICK_MODE", raising=False)
    calls: list[tuple[str, bool, bool]] = []
    monkeypatch.setattr(sync, "flush_qrhi_compositor", _flush_mock(calls))
    scheduled: list[tuple[int, object]] = []
    import PySide6.QtCore as core

    monkeypatch.setattr(core.QTimer, "singleShot", _singleshot_mock(scheduled))

    w, _state = _widget(visible=True)
    wmod._schedule_drag_restack(w)
    assert [ms for ms, _ in scheduled] == [wmod._DND_RESTACK_FIRST_MS]

    _drain(scheduled)

    assert len(calls) == wmod._DND_RESTACK_MAX_KICKS
    assert all(r == "ic-dnd-show-settle" and a is False for r, a, _c in calls)
    assert all(c is True for _r, _a, c in calls)  # default full mode
    assert scheduled == []


def test_restack_chain_light_mode_skips_chrome(monkeypatch):
    from tabs.image_compare.canvas import widget as wmod
    from ui.canvas_infra.rhi import rhi_present_sync as sync

    monkeypatch.setenv("IMGSLI_DND_KICK_MODE", "light")
    calls: list[tuple[str, bool, bool]] = []
    monkeypatch.setattr(sync, "flush_qrhi_compositor", _flush_mock(calls))
    scheduled: list[tuple[int, object]] = []
    import PySide6.QtCore as core

    monkeypatch.setattr(core.QTimer, "singleShot", _singleshot_mock(scheduled))

    w, _state = _widget(visible=True)
    wmod._schedule_drag_restack(w)
    _drain(scheduled)

    assert len(calls) == wmod._DND_RESTACK_MAX_KICKS
    assert all(a is False and c is False for _r, a, c in calls)


def test_restack_chain_stops_when_hidden(monkeypatch):
    from tabs.image_compare.canvas import widget as wmod
    from ui.canvas_infra.rhi import rhi_present_sync as sync

    monkeypatch.delenv("IMGSLI_DND_KICK_MODE", raising=False)
    calls: list[tuple[str, bool, bool]] = []
    monkeypatch.setattr(sync, "flush_qrhi_compositor", _flush_mock(calls))
    scheduled: list[tuple[int, object]] = []
    import PySide6.QtCore as core

    monkeypatch.setattr(core.QTimer, "singleShot", _singleshot_mock(scheduled))

    w, state = _widget(visible=True)
    wmod._schedule_drag_restack(w)
    # Drag ends before the first kick fires: no flush, no re-arm.
    state._drag_overlay_visible = False
    _drain(scheduled)

    assert calls == []
    assert scheduled == []


def test_restack_chain_stops_midway_when_hidden(monkeypatch):
    from tabs.image_compare.canvas import widget as wmod
    from ui.canvas_infra.rhi import rhi_present_sync as sync

    monkeypatch.delenv("IMGSLI_DND_KICK_MODE", raising=False)
    calls: list[tuple[str, bool, bool]] = []
    monkeypatch.setattr(sync, "flush_qrhi_compositor", _flush_mock(calls))
    scheduled: list[tuple[int, object]] = []
    import PySide6.QtCore as core

    monkeypatch.setattr(core.QTimer, "singleShot", _singleshot_mock(scheduled))

    w, state = _widget(visible=True)
    wmod._schedule_drag_restack(w)
    _ms, first = scheduled.pop(0)
    first()
    assert len(calls) == 1
    # Hide between kicks: the armed repeat must stand down.
    state._drag_overlay_visible = False
    _drain(scheduled)
    assert len(calls) == 1
    assert scheduled == []
