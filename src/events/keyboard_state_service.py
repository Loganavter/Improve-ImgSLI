from __future__ import annotations

from dataclasses import dataclass
import logging

from PyQt6.QtCore import Qt

logger = logging.getLogger("ImproveImgSLI")

@dataclass(slots=True, frozen=True)
class KeyboardStateResult:
    applied: bool
    reason: str

class KeyboardStateService:
    MAGNIFIER_KEYS = {
        Qt.Key.Key_A,
        Qt.Key.Key_D,
        Qt.Key.Key_W,
        Qt.Key.Key_S,
        Qt.Key.Key_Q,
        Qt.Key.Key_E,
    }

    def __init__(self, store):
        self.store = store

    @property
    def interaction(self):
        return self.store.viewport.interaction_state

    @classmethod
    def is_managed_key(cls, key_code: int) -> bool:
        return key_code == Qt.Key.Key_Space or key_code in cls.MAGNIFIER_KEYS

    def has_active_magnifier_keys(self) -> bool:
        return any(key in self.interaction.pressed_keys for key in self.MAGNIFIER_KEYS)

    def press(self, key_code: int, *, is_auto_repeat: bool = False) -> KeyboardStateResult:
        interaction = self.interaction
        if not self.is_managed_key(key_code):
            return KeyboardStateResult(False, "ignored_untracked")
        if key_code == Qt.Key.Key_Space:
            if is_auto_repeat:
                return KeyboardStateResult(False, "space_auto_repeat")
            if interaction.space_bar_pressed:
                return KeyboardStateResult(False, "space_duplicate")
            interaction.space_bar_pressed = True
            return KeyboardStateResult(True, "space_pressed")

        if key_code in self.MAGNIFIER_KEYS and is_auto_repeat:
            return KeyboardStateResult(False, "magnifier_auto_repeat")
        if key_code in interaction.pressed_keys:
            return KeyboardStateResult(False, "duplicate_press")

        interaction.pressed_keys.add(key_code)
        self._update_axis_priority_on_press(key_code)
        self._log_state("press", key_code)
        return KeyboardStateResult(True, "pressed")

    def release(self, key_code: int, *, is_auto_repeat: bool = False) -> KeyboardStateResult:
        interaction = self.interaction
        if not self.is_managed_key(key_code):
            return KeyboardStateResult(False, "ignored_untracked")
        if key_code == Qt.Key.Key_Space:
            if is_auto_repeat:
                return KeyboardStateResult(False, "space_auto_repeat")
            if not interaction.space_bar_pressed:
                return KeyboardStateResult(False, "space_stray_release")
            interaction.space_bar_pressed = False
            return KeyboardStateResult(True, "space_released")

        if key_code in self.MAGNIFIER_KEYS and is_auto_repeat:
            return KeyboardStateResult(False, "magnifier_auto_repeat")
        if key_code not in interaction.pressed_keys:
            return KeyboardStateResult(False, "stray_release")

        interaction.pressed_keys.discard(key_code)
        self._update_axis_priority_on_release(key_code)
        self._log_state("release", key_code)
        return KeyboardStateResult(True, "released")

    def reset(self) -> KeyboardStateResult:
        interaction = self.interaction
        if (
            not interaction.pressed_keys
            and not interaction.space_bar_pressed
            and interaction.last_horizontal_movement_key is None
            and interaction.last_vertical_movement_key is None
            and interaction.last_spacing_movement_key is None
        ):
            return KeyboardStateResult(False, "already_clear")

        interaction.pressed_keys.clear()
        interaction.space_bar_pressed = False
        interaction.last_horizontal_movement_key = None
        interaction.last_vertical_movement_key = None
        interaction.last_spacing_movement_key = None
        self._log_state("reset", None)
        return KeyboardStateResult(True, "reset")

    def _log_state(self, action: str, key_code: int | None) -> None:
        interaction = self.interaction
        managed_pressed = sorted(
            int(key)
            for key in interaction.pressed_keys
            if key in self.MAGNIFIER_KEYS
        )
        logger.warning(
            "KeyboardState %s key=%s pressed=%s horiz=%s vert=%s spacing=%s space=%s",
            action,
            None if key_code is None else int(key_code),
            managed_pressed,
            None
            if interaction.last_horizontal_movement_key is None
            else int(interaction.last_horizontal_movement_key),
            None
            if interaction.last_vertical_movement_key is None
            else int(interaction.last_vertical_movement_key),
            None
            if interaction.last_spacing_movement_key is None
            else int(interaction.last_spacing_movement_key),
            bool(interaction.space_bar_pressed),
        )

    def _update_axis_priority_on_press(self, key_code: int) -> None:
        interaction = self.interaction
        if key_code in (Qt.Key.Key_A, Qt.Key.Key_D):
            interaction.last_horizontal_movement_key = key_code
        elif key_code in (Qt.Key.Key_W, Qt.Key.Key_S):
            interaction.last_vertical_movement_key = key_code
        elif key_code in (Qt.Key.Key_Q, Qt.Key.Key_E):
            interaction.last_spacing_movement_key = key_code

    def _update_axis_priority_on_release(self, key_code: int) -> None:
        interaction = self.interaction
        if key_code in (Qt.Key.Key_A, Qt.Key.Key_D):
            if interaction.last_horizontal_movement_key == key_code:
                opposite = Qt.Key.Key_D if key_code == Qt.Key.Key_A else Qt.Key.Key_A
                interaction.last_horizontal_movement_key = (
                    opposite if opposite in interaction.pressed_keys else None
                )
        elif key_code in (Qt.Key.Key_W, Qt.Key.Key_S):
            if interaction.last_vertical_movement_key == key_code:
                opposite = Qt.Key.Key_S if key_code == Qt.Key.Key_W else Qt.Key.Key_W
                interaction.last_vertical_movement_key = (
                    opposite if opposite in interaction.pressed_keys else None
                )
        elif key_code in (Qt.Key.Key_Q, Qt.Key.Key_E):
            if interaction.last_spacing_movement_key == key_code:
                opposite = Qt.Key.Key_E if key_code == Qt.Key.Key_Q else Qt.Key.Key_Q
                interaction.last_spacing_movement_key = (
                    opposite if opposite in interaction.pressed_keys else None
                )
