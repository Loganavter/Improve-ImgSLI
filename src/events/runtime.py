from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from PyQt6.QtCore import QTimer

from events.app_event import GlobalKeyboardHandler
from events.app_event.null_movement import NullKeyboardMovementController
from events.keyboard_state_service import KeyboardStateService
from ui.canvas_infra.scene.widget_registry import get_canvas_feature_command_by_alias

@dataclass(slots=True)
class EventHandlerRuntime:
    interactive_movement: Any
    keyboard_handler: GlobalKeyboardHandler
    keyboard_state: KeyboardStateService
    resize_timer: QTimer

def _build_movement_controller(store, presenter_provider, parent):
    build = get_canvas_feature_command_by_alias("keyboard_movement.build_controller")
    if build is None:
        return NullKeyboardMovementController()
    try:
        return build(store, presenter_provider=presenter_provider, parent=parent)
    except Exception:
        return NullKeyboardMovementController()

def build_event_handler_runtime(store, presenter_provider, parent=None) -> EventHandlerRuntime:
    interactive_movement = _build_movement_controller(store, presenter_provider, parent)
    keyboard_state = KeyboardStateService(store)
    keyboard_handler = GlobalKeyboardHandler(
        store,
        presenter_provider=presenter_provider,
        movement_controller=interactive_movement,
        keyboard_state=keyboard_state,
    )
    resize_timer = QTimer(parent)
    resize_timer.setSingleShot(True)
    return EventHandlerRuntime(
        interactive_movement=interactive_movement,
        keyboard_handler=keyboard_handler,
        keyboard_state=keyboard_state,
        resize_timer=resize_timer,
    )
