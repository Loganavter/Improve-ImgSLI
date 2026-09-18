"""Source-side no-op gate for magnifier geometry dispatches.

Live trace 2026-09-18: 152/195 empty-diff ``dispatch.end`` came from
``_dispatch_magnifier_geometry`` (76 ``SET_MAGNIFIER_SCREEN_CENTER`` + 76
``SET_MAGNIFIER_SCREEN_SIZE``). The reducer/dispatcher identity guards
already drop equal-valued dispatches, but ``traced_dispatch`` still logs
begin/end for every call. This gate skips the call entirely when the value
is unchanged, so the trace storm disappears without any observable state,
emit, or history change (see ``tests/runtime/test_noop_dispatch_dropped.py``
for the layers that already made equal dispatches inert).
"""

from __future__ import annotations

from types import SimpleNamespace

from domain.types import Point

from tabs.image_compare.canvas.features.magnifier.scene.apply import (
    _dispatch_magnifier_geometry,
)


class _RecordingDispatcher:
    def __init__(self):
        self.dispatched: list = []

    def dispatch(self, action, scope: str = "viewport"):
        self.dispatched.append((action, scope))


class _FakeStore:
    """Mirrors the fake-store style of test_noop_dispatch_dropped.py."""

    def __init__(self, dispatcher: _RecordingDispatcher):
        self._dispatcher = dispatcher
        self.batch_entered = 0

    def get_dispatcher(self):
        return self._dispatcher

    def batch_changes(self):
        store = self

        class _BatchCtx:
            def __enter__(self_inner):
                store.batch_entered += 1
                return self_inner

            def __exit__(self_inner, *exc):
                return False

        return _BatchCtx()


def _geometry_state(center: Point, size: int) -> SimpleNamespace:
    return SimpleNamespace(
        active_overlay_screen_center=center,
        active_overlay_screen_size=size,
    )


def _dispatch_types(dispatcher: _RecordingDispatcher) -> list:
    return [type(action).__name__ for action, _scope in dispatcher.dispatched]


def _make(center: Point, size: int):
    dispatcher = _RecordingDispatcher()
    store = _FakeStore(dispatcher)
    return dispatcher, store, _geometry_state(center, size)


def test_equal_center_and_size_dispatches_nothing_and_does_not_batch():
    center = Point(10.0, 20.0)
    dispatcher, store, geometry_state = _make(center, 5)

    result = _dispatch_magnifier_geometry(geometry_state, center, 5, store)

    assert result is True
    assert dispatcher.dispatched == [], _dispatch_types(dispatcher)
    assert store.batch_entered == 0, "no-op must not open store.batch_changes()"


def test_changed_center_only_dispatches_center():
    dispatcher, store, geometry_state = _make(Point(1.0, 2.0), 5)

    _dispatch_magnifier_geometry(geometry_state, Point(9.0, 9.0), 5, store)

    assert _dispatch_types(dispatcher) == ["SetMagnifierScreenCenterAction"]
    assert store.batch_entered == 1


def test_changed_size_only_dispatches_size():
    dispatcher, store, geometry_state = _make(Point(1.0, 2.0), 5)

    _dispatch_magnifier_geometry(geometry_state, Point(1.0, 2.0), 11, store)

    assert _dispatch_types(dispatcher) == ["SetMagnifierScreenSizeAction"]
    assert store.batch_entered == 1


def test_both_changed_dispatches_center_then_size():
    dispatcher, store, geometry_state = _make(Point(1.0, 2.0), 5)

    _dispatch_magnifier_geometry(geometry_state, Point(9.0, 9.0), 11, store)

    assert _dispatch_types(dispatcher) == [
        "SetMagnifierScreenCenterAction",
        "SetMagnifierScreenSizeAction",
    ]
    assert store.batch_entered == 1


class _GeometryProbe(SimpleNamespace):
    def __init__(self, center: Point, size: int):
        super().__setattr__("writes", [])
        super().__setattr__("active_overlay_screen_center", center)
        super().__setattr__("active_overlay_screen_size", size)

    def __setattr__(self, name, value):
        self.writes.append((name, value))
        super().__setattr__(name, value)


def test_no_dispatcher_fallback_gates_equal_values():
    center = Point(1.0, 2.0)
    geometry_state = _GeometryProbe(center, 5)
    store = SimpleNamespace(get_dispatcher=lambda: None)

    result = _dispatch_magnifier_geometry(geometry_state, center, 5, store)

    assert result is False
    assert geometry_state.writes == [], "equal values must not trigger fallback setattr"


def test_no_dispatcher_fallback_writes_only_changed_field():
    geometry_state = _GeometryProbe(Point(1.0, 2.0), 5)
    store = SimpleNamespace(get_dispatcher=lambda: None)

    _dispatch_magnifier_geometry(geometry_state, Point(9.0, 9.0), 5, store)

    assert geometry_state.writes == [
        ("active_overlay_screen_center", Point(9.0, 9.0))
    ]
