from __future__ import annotations

from dataclasses import dataclass, field

@dataclass(slots=True)
class CanvasInputSessionState:
    active_owners: set[str] = field(default_factory=set)

    def is_active(self) -> bool:
        return bool(self.active_owners)

class CanvasInputSessionService:
    def __init__(self, main_controller):
        self.main_controller = main_controller
        self.state = CanvasInputSessionState()

    def has_owner(self, owner: str) -> bool:
        return owner in self.state.active_owners

    def activate(self, owner: str) -> bool:
        was_active = self.state.is_active()
        self.state.active_owners.add(owner)
        is_active = self.state.is_active()
        if not was_active and is_active:
            self._emit_start()
        return not was_active and is_active

    def deactivate(self, owner: str) -> bool:
        was_active = self.state.is_active()
        self.state.active_owners.discard(owner)
        is_active = self.state.is_active()
        if was_active and not is_active:
            self._emit_stop()
        return was_active and not is_active

    def reset(self) -> bool:
        if not self.state.active_owners:
            return False
        self.state.active_owners.clear()
        self._emit_stop()
        return True

    def _emit_start(self) -> None:
        if self.main_controller is not None:
            self.main_controller.start_interactive_movement.emit()

    def _emit_stop(self) -> None:
        if self.main_controller is not None:
            self.main_controller.stop_interactive_movement.emit()
