"""EventBus re-entrancy depth guard.

A subscriber that re-publishes the same event creates a circular chain. The bus
must stop it at ``MAX_EMIT_DEPTH`` with a clear error instead of hanging or
raising a bare ``RecursionError``.

Dogma source: docs/dev/ARCHITECTURE.md / CLAUDE memory ("watch EventBus depth,
max 10 levels").
"""

from __future__ import annotations

import pytest

from core.events import Event
from core.plugin_system.event_bus import (
    MAX_EMIT_DEPTH,
    EventBus,
    EventBusDepthExceeded,
)

class _PingEvent(Event):
    pass

def test_circular_chain_stops_at_max_depth():
    bus = EventBus()
    emits: list[int] = []

    def handler(_event):
        emits.append(1)
        bus.emit(_PingEvent())

    bus.subscribe(_PingEvent, handler)

    with pytest.raises(EventBusDepthExceeded):
        bus.emit(_PingEvent())

    assert len(emits) == MAX_EMIT_DEPTH

def test_depth_counter_resets_between_top_level_emits():
    bus = EventBus()
    calls: list[int] = []
    bus.subscribe(_PingEvent, lambda _e: calls.append(1))

    bus.emit(_PingEvent())
    bus.emit(_PingEvent())

    assert len(calls) == 2

def test_shallow_nesting_is_allowed():
    bus = EventBus()
    seen: list[str] = []

    class _AEvent(Event):
        pass

    class _BEvent(Event):
        pass

    def on_a(_e):
        seen.append("a")
        bus.emit(_BEvent())

    def on_b(_e):
        seen.append("b")

    bus.subscribe(_AEvent, on_a)
    bus.subscribe(_BEvent, on_b)

    bus.emit(_AEvent())
    assert seen == ["a", "b"]
