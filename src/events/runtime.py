from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import QTimer

from events.app_event import GlobalKeyboardHandler, InteractiveMovementController

@dataclass(slots=True)
class EventHandlerRuntime:
    interactive_movement: InteractiveMovementController
    keyboard_handler: GlobalKeyboardHandler
    resize_timer: QTimer

def build_event_handler_runtime(store, presenter_provider, parent=None) -> EventHandlerRuntime:
    interactive_movement = InteractiveMovementController(
        store,
        presenter_provider=presenter_provider,
        parent=parent,
    )
    keyboard_handler = GlobalKeyboardHandler(
        store,
        presenter_provider=presenter_provider,
        movement_controller=interactive_movement,
    )
    resize_timer = QTimer(parent)
    resize_timer.setSingleShot(True)
    return EventHandlerRuntime(
        interactive_movement=interactive_movement,
        keyboard_handler=keyboard_handler,
        resize_timer=resize_timer,
    )
