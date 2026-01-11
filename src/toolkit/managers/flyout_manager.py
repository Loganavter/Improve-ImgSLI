from typing import Optional, Set, TYPE_CHECKING

if TYPE_CHECKING:
    from toolkit.widgets.composite.base_flyout import BaseFlyout

from PyQt6.QtCore import QObject

class FlyoutManager(QObject):

    _instance: Optional['FlyoutManager'] = None

    def __init__(self):
        super().__init__()
        self._active_flyout: Optional['BaseFlyout'] = None
        self._registered_flyouts: Set['BaseFlyout'] = set()

    @classmethod
    def get_instance(cls) -> 'FlyoutManager':
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register_flyout(self, flyout: 'BaseFlyout'):
        if flyout not in self._registered_flyouts:
            self._registered_flyouts.add(flyout)

    def unregister_flyout(self, flyout: 'BaseFlyout'):
        self._registered_flyouts.discard(flyout)
        if self._active_flyout is flyout:
            self._active_flyout = None

    def request_show(self, flyout: 'BaseFlyout') -> bool:
        if flyout not in self._registered_flyouts:

            self.register_flyout(flyout)

        if self._active_flyout is flyout and flyout.isVisible():
            return True

        if self._active_flyout is not None and self._active_flyout.isVisible():
            try:
                self._active_flyout.hide()
            except Exception as e:
                pass

        self._active_flyout = flyout
        return True

    def request_hide(self, flyout: 'BaseFlyout'):
        if self._active_flyout is flyout:
            self._active_flyout = None

    def close_all(self):
        if self._active_flyout is not None and self._active_flyout.isVisible():
            try:
                self._active_flyout.hide()
            except Exception:
                pass
        self._active_flyout = None

    def is_flyout_active(self, flyout: 'BaseFlyout') -> bool:
        return self._active_flyout is flyout and flyout.isVisible()

    def get_active_flyout(self) -> Optional['BaseFlyout']:
        if self._active_flyout is not None and self._active_flyout.isVisible():
            return self._active_flyout
        return None

