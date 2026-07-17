from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from events.app_event import GlobalKeyboardHandler
from events.app_event.null_movement import NullKeyboardMovementController
from events.keyboard_state_service import KeyboardStateService
from ui.canvas_infra.scene.registry import get_canvas_registry

@dataclass(slots=True)
class EventHandlerRuntime:
    interactive_movement: Any
    keyboard_handler: GlobalKeyboardHandler
    keyboard_state: KeyboardStateService

class _LazyKeyboardMovementController:
    """Resolves the real per-session movement controller on first use.

    The active session at ``EventHandler`` construction time is always the
    session-picker placeholder, which never registers
    ``keyboard_movement.build_controller``. Building eagerly at that point
    permanently freezes this on the no-op stub. Instead, resolve (and cache
    per session type) lazily so switching into a real image-compare session
    picks up the real controller.
    """

    def __init__(self, store, presenter_provider, parent):
        self._store = store
        self._presenter_provider = presenter_provider
        self._parent = parent
        self._built_by_session_type: dict[str, Any] = {}

    def _resolve(self):
        session = self._store.get_active_workspace_session()
        session_type = session.session_type if session is not None else None
        cached = self._built_by_session_type.get(session_type)
        if cached is not None:
            return cached
        build = get_canvas_registry(session_type).get_feature_command_by_alias(
            "keyboard_movement.build_controller"
        )
        if build is None:
            controller = NullKeyboardMovementController()
        else:
            try:
                controller = build(
                    self._store,
                    presenter_provider=self._presenter_provider,
                    parent=self._parent,
                )
            except Exception:
                controller = NullKeyboardMovementController()
        self._built_by_session_type[session_type] = controller
        return controller

    def start(self) -> None:
        self._resolve().start()

    def stop(self) -> None:
        self._resolve().stop()

def _build_movement_controller(store, presenter_provider, parent):
    return _LazyKeyboardMovementController(store, presenter_provider, parent)

def build_event_handler_runtime(store, presenter_provider, parent=None) -> EventHandlerRuntime:
    interactive_movement = _build_movement_controller(store, presenter_provider, parent)
    keyboard_state = KeyboardStateService(store)
    keyboard_handler = GlobalKeyboardHandler(
        store,
        presenter_provider=presenter_provider,
        movement_controller=interactive_movement,
        keyboard_state=keyboard_state,
    )
    return EventHandlerRuntime(
        interactive_movement=interactive_movement,
        keyboard_handler=keyboard_handler,
        keyboard_state=keyboard_state,
    )
