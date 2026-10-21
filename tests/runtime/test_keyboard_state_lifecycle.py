"""Keyboard-state lifecycle: tab-switch resets, session-pinned Shift, NaN-safe speed.

Guards: held keys never leak across an intra-window tab switch (lazy
session pin in KeyboardStateService + panel FocusOut reset), Shift-preview
snapshots restore only into the pinning session (fail-closed unwind
otherwise), movement-controller build failures never poison the runtime
cache, and speed/dt inputs are finite/range-guarded.

Covers the tab-switch mid-hold, cross-session Shift, and NaN speed cases.
"""

from __future__ import annotations

import math
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QFocusEvent
from PySide6.QtWidgets import QWidget

from events.keyboard_state_service import KeyboardStateService


@pytest.fixture(autouse=True)
def _reset_dnd_singletons(monkeypatch):
    from events.drag_drop_handler import DragAndDropService
    from events.image_carry import ImageCarryService

    monkeypatch.setattr(DragAndDropService, "_instance", None)
    monkeypatch.setattr(ImageCarryService, "_instance", None)
    yield
    DragAndDropService._instance = None
    ImageCarryService._instance = None


def _interaction():
    return SimpleNamespace(
        pressed_keys=set(),
        space_bar_pressed=False,
        last_horizontal_movement_key=None,
        last_vertical_movement_key=None,
        last_spacing_movement_key=None,
    )


def _session_store(session_id="sA", *, with_sessions=True):
    holder = {"id": session_id}
    interaction = _interaction()
    emits: list[str] = []
    store = SimpleNamespace(
        viewport=SimpleNamespace(
            interaction_state=interaction,
            view_state=SimpleNamespace(),
        ),
        emit_viewport_change=lambda scope: emits.append(scope),
    )
    if with_sessions:
        store.get_active_workspace_session = lambda: SimpleNamespace(
            session_type="img", id=holder["id"]
        )
    return store, holder, interaction, emits


def test_tab_switch_mid_hold_resets_keys():
    """Press W (tab A), switch to B mid-hold: B never inherits the hold."""
    store, holder, interaction, emits = _session_store("sA")
    svc = KeyboardStateService(store)

    assert svc.press(Qt.Key.Key_W).applied
    assert interaction.pressed_keys == {Qt.Key.Key_W}

    holder["id"] = "sB"
    result = svc.release(Qt.Key.Key_W)

    assert result.reason == "stray_release"
    assert interaction.pressed_keys == set()
    assert interaction.last_horizontal_movement_key is None
    assert interaction.last_vertical_movement_key is None
    assert interaction.last_spacing_movement_key is None
    assert "interaction" in emits  # auto-reset announced itself

    # Re-pinned to B: fresh presses work there.
    assert svc.press(Qt.Key.Key_D).applied
    assert svc._session_id == "sB"


def test_sessionless_store_keeps_legacy_behavior():
    """Stores without session identity skip pinning entirely (fail-open)."""
    store, _holder, interaction, _emits = _session_store(with_sessions=False)
    svc = KeyboardStateService(store)

    assert svc.press(Qt.Key.Key_W).applied
    assert svc.release(Qt.Key.Key_W).applied
    assert svc._session_id is None
    assert interaction.pressed_keys == set()


def test_stray_release_clears_stale_axis_pointer():
    """Desynced last_* pointer naming an unheld key is cleared on stray."""
    store, _holder, interaction, _emits = _session_store("sA")
    svc = KeyboardStateService(store)
    interaction.last_vertical_movement_key = int(Qt.Key.Key_W)

    result = svc.release(Qt.Key.Key_W)

    assert result.reason == "stray_release"
    assert interaction.last_vertical_movement_key is None


def _preview_handler(holder):
    store = SimpleNamespace(
        get_active_workspace_session=lambda: SimpleNamespace(
            session_type="img", id=holder["id"]
        ),
        emit_state_change=lambda *a, **k: None,
    )
    return SimpleNamespace(store=store, event_bus=None, main_controller=None)


def _preview_registry(monkeypatch):
    import events.image_label.preview as preview_mod

    state = {
        "snapshot": {"side": "left", "mode": "rgb"},
        "restore_calls": [],
        "restore_impl": None,
    }

    class _FakeRegistry:
        def get_feature_command_by_alias(self, alias):
            if alias == "preview.snapshot":
                return lambda _store: dict(state["snapshot"])
            if alias == "preview.restore":
                def _restore(_store, **kwargs):
                    state["restore_calls"].append(dict(kwargs))
                    impl = state["restore_impl"]
                    if impl is not None:
                        return impl(**kwargs)
                    return True

                return _restore
            return None

    monkeypatch.setattr(
        preview_mod, "get_canvas_registry", lambda _session_type: _FakeRegistry()
    )
    return state


def test_cross_session_shift_discards_snapshot(monkeypatch):
    """Begin on A, switch to B mid-hold: restore applies nothing (closed)."""
    from events.image_label.preview import OverlayPreviewController

    holder = {"id": "sA"}
    controller = OverlayPreviewController(_preview_handler(holder))
    state = _preview_registry(monkeypatch)
    controller.begin()
    assert controller.is_active

    holder["id"] = "sB"
    controller.restore()

    assert state["restore_calls"] == []
    assert not controller.is_active


def test_same_session_shift_restores_payload_identity(monkeypatch):
    """Begin/restore in one session applies the exact snapshot payload."""
    from events.image_label.preview import OverlayPreviewController

    holder = {"id": "sA"}
    controller = OverlayPreviewController(_preview_handler(holder))
    state = _preview_registry(monkeypatch)
    controller.begin()

    controller.restore()

    assert state["restore_calls"] == [{"side": "left", "mode": "rgb"}]
    assert not controller.is_active


def test_failed_restore_unwinds_without_propagating(monkeypatch):
    """Throwing restore command: no exception escapes, gesture unwinds."""
    from events.image_label.preview import OverlayPreviewController

    holder = {"id": "sA"}
    controller = OverlayPreviewController(_preview_handler(holder))
    state = _preview_registry(monkeypatch)

    def _boom(**kwargs):
        raise RuntimeError("restore exploded")

    state["restore_impl"] = _boom
    controller.begin()

    controller.restore()  # must not raise

    assert not controller.is_active
    assert len(state["restore_calls"]) == 1


def test_nan_speed_applies_no_motion():
    """NaN speed/dt: offsets and spacing stay exactly put, never NaN."""
    from domain.types import Point
    from events.app_event.interactive_movement_input import (
        MovementDirections,
        apply_offset_input,
        apply_spacing_input,
        compute_speed_factor,
    )

    dirs = MovementDirections(dx=1, dy=0, ds=0)
    offset = Point(10.0, 20.0)

    new_offset, changed = apply_offset_input(offset, dirs, float("nan"), 0.016)
    assert not changed
    assert (new_offset.x, new_offset.y) == (10.0, 20.0)

    new_offset, changed = apply_offset_input(offset, dirs, 1.0, float("nan"))
    assert not changed
    assert (new_offset.x, new_offset.y) == (10.0, 20.0)

    new_offset, changed = apply_offset_input(offset, dirs, 1.0, -0.5)
    assert not changed
    assert (new_offset.x, new_offset.y) == (10.0, 20.0)

    spacing, changed = apply_spacing_input(
        1.0, 1, float("nan"), 0.016, min_spacing=0.0, max_spacing=2.0
    )
    assert (spacing, changed) == (1.0, False)
    assert math.isfinite(spacing)

    assert compute_speed_factor(SimpleNamespace(movement_speed_per_sec=float("nan"))) == 0.0
    # Honor-defaults identity: stock setting 2.0 x base 0.5 == 1.0 scale.
    assert compute_speed_factor(SimpleNamespace(movement_speed_per_sec=2.0)) == 1.0


def test_huge_dt_is_clamped_not_teleported():
    """A 10 s clock jump moves at most one backstop step, finitely."""
    from domain.types import Point
    from events.app_event.interactive_movement_input import (
        MovementDirections,
        apply_offset_input,
    )

    dirs = MovementDirections(dx=1, dy=0, ds=0)
    new_offset, changed = apply_offset_input(Point(0.0, 0.0), dirs, 1.0, 10.0)

    assert changed
    assert new_offset.x == pytest.approx(0.1)
    assert math.isfinite(new_offset.x)


def test_runtime_build_failure_retries_instead_of_poisoning(monkeypatch):
    """A throwing build is not cached: the next resolve retries cleanly."""
    import events.runtime as runtime_mod
    from events.app_event.null_movement import NullKeyboardMovementController
    from events.runtime import _LazyKeyboardMovementController

    holder = {"build": None}
    store = SimpleNamespace(
        get_active_workspace_session=lambda: SimpleNamespace(
            session_type="img", id="s1"
        )
    )

    class _FakeRegistry:
        def get_feature_command_by_alias(self, _alias):
            return holder["build"]

    monkeypatch.setattr(
        runtime_mod, "get_canvas_registry", lambda _session_type: _FakeRegistry()
    )
    controller = _LazyKeyboardMovementController(store, lambda: None, None)

    def _raising(_store, presenter_provider=None, parent=None):
        raise RuntimeError("boom")

    working = SimpleNamespace(start=lambda: None, stop=lambda: None)

    def _working(_store, presenter_provider=None, parent=None):
        return working

    holder["build"] = _raising
    first = controller._resolve()
    assert isinstance(first, NullKeyboardMovementController)

    holder["build"] = _working
    assert controller._resolve() is working


def test_runtime_missing_alias_caches_stable_null(monkeypatch):
    """No alias is a stable fallback (cached); only failures retry."""
    import events.runtime as runtime_mod
    from events.runtime import _LazyKeyboardMovementController

    store = SimpleNamespace(
        get_active_workspace_session=lambda: SimpleNamespace(
            session_type="picker", id="s0"
        )
    )

    class _FakeRegistry:
        def get_feature_command_by_alias(self, _alias):
            return None

    monkeypatch.setattr(
        runtime_mod, "get_canvas_registry", lambda _session_type: _FakeRegistry()
    )
    controller = _LazyKeyboardMovementController(store, lambda: None, None)

    assert controller._resolve() is controller._resolve()


def test_panel_focusout_resets_held_keys(qapp):
    """FocusOut on any panel (not just the main window) clears held keys."""
    from events.app_event_handler import EventHandler
    from events.drag_drop_handler import DragAndDropService

    doc = SimpleNamespace(image_list1=[], image_list2=[])
    DragAndDropService(
        SimpleNamespace(get_session_state_slot=lambda _slot: doc), parent=None
    )
    store, _holder, interaction, emits = _session_store("sA")
    interaction.pressed_keys.add(int(Qt.Key.Key_W))
    interaction.last_horizontal_movement_key = int(Qt.Key.Key_W)
    session_resets: list[int] = []
    presenter = SimpleNamespace(
        main_window_app=object(),
        image_label_handler=SimpleNamespace(
            input_session=SimpleNamespace(
                reset=lambda: (session_resets.append(1), True)[1]
            )
        ),
    )
    handler = EventHandler(store, presenter)

    panel = QWidget()
    assert handler.eventFilter(panel, QFocusEvent(QEvent.Type.FocusOut)) is False
    # The reset decision is deferred one turn: FocusOut arrives before the new
    # focus owner exists (a click moves focus shell -> canvas -> shell, and the
    # old synchronous reset cleared Space between the key and its click).
    qapp.processEvents()

    assert interaction.pressed_keys == set()
    assert interaction.last_horizontal_movement_key is None
    assert emits == ["interaction"]
    assert session_resets == [1]
    panel.deleteLater()


def test_idle_focusout_emits_nothing(qapp):
    """FocusOut with nothing held is a silent no-op (no spurious emits)."""
    from events.app_event_handler import EventHandler
    from events.drag_drop_handler import DragAndDropService

    doc = SimpleNamespace(image_list1=[], image_list2=[])
    DragAndDropService(
        SimpleNamespace(get_session_state_slot=lambda _slot: doc), parent=None
    )
    store, _holder, _interaction, emits = _session_store("sA")
    presenter = SimpleNamespace(
        main_window_app=object(),
        image_label_handler=SimpleNamespace(
            input_session=SimpleNamespace(reset=lambda: False)
        ),
    )
    handler = EventHandler(store, presenter)

    panel = QWidget()
    assert handler.eventFilter(panel, QFocusEvent(QEvent.Type.FocusOut)) is False
    qapp.processEvents()

    assert emits == []
    panel.deleteLater()
