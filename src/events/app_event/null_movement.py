"""No-op keyboard-movement controller.

Used when no feature registers ``keyboard_movement.build_controller``. Lets
``EventHandlerRuntime`` ship a controller with the same surface regardless of
which features are present — shared event code calls ``start()``/``stop()``
unconditionally.
"""

from __future__ import annotations

class NullKeyboardMovementController:
    """Drop-in stub matching the controller protocol: only ``start``/``stop``."""

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass
