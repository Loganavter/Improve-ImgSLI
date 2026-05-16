from typing import Optional, Protocol, Set

from PyQt6.QtCore import QObject

class ManagedFlyout(Protocol):
    def isVisible(self) -> bool: ...
    def hide(self) -> None: ...

class FlyoutManager(QObject):
    _instance: Optional["FlyoutManager"] = None

    def __init__(self):
        super().__init__()
        self._active_flyout: Optional[ManagedFlyout] = None
        self._registered_flyouts: Set[ManagedFlyout] = set()

    @classmethod
    def get_instance(cls) -> "FlyoutManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register_flyout(self, flyout: ManagedFlyout):
        if flyout not in self._registered_flyouts:
            self._registered_flyouts.add(flyout)

    def unregister_flyout(self, flyout: ManagedFlyout):
        self._registered_flyouts.discard(flyout)
        if self._active_flyout is flyout:
            self._active_flyout = None

    def request_show(self, flyout: ManagedFlyout) -> bool:
        if flyout not in self._registered_flyouts:
            self.register_flyout(flyout)

        if self._active_flyout is flyout and flyout.isVisible():
            return True

        if self._active_flyout is not None and self._active_flyout.isVisible():
            try:
                self._active_flyout.hide()
            except Exception:
                pass

        self._active_flyout = flyout
        return True

    def request_hide(self, flyout: ManagedFlyout):
        if self._active_flyout is flyout:
            self._active_flyout = None

    def close_all(self):
        if self._active_flyout is not None and self._active_flyout.isVisible():
            try:
                self._active_flyout.hide()
            except Exception:
                pass
        self._active_flyout = None

    def is_flyout_active(self, flyout: ManagedFlyout) -> bool:
        return self._active_flyout is flyout and flyout.isVisible()

    def get_active_flyout(self) -> Optional[ManagedFlyout]:
        if self._active_flyout is not None and self._active_flyout.isVisible():
            return self._active_flyout
        return None

