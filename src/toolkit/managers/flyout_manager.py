from typing import Optional, Set, TYPE_CHECKING

if TYPE_CHECKING:
    from toolkit.widgets.composite.base_flyout import BaseFlyout

from PyQt6.QtCore import QObject, QTimer
from PyQt6.QtWidgets import QApplication, QWidget

class FlyoutManager(QObject):

    _instance: Optional['FlyoutManager'] = None

    def __init__(self):
        super().__init__()
        self._active_flyout: Optional['BaseFlyout'] = None
        self._registered_flyouts: Set['BaseFlyout'] = set()

        self._focus_lost_timer = QTimer(self)
        self._focus_lost_timer.setSingleShot(True)
        self._focus_lost_timer.setInterval(100)
        self._focus_lost_timer.timeout.connect(self._on_focus_lost_timeout)

        app = QApplication.instance()
        if app:
            app.focusChanged.connect(self._on_focus_changed)

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
            self._focus_lost_timer.stop()

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

        self._focus_lost_timer.stop()
        return True

    def request_hide(self, flyout: 'BaseFlyout'):
        if self._active_flyout is flyout:
            self._active_flyout = None
            self._focus_lost_timer.stop()

    def close_all(self):
        if self._active_flyout is not None and self._active_flyout.isVisible():
            try:
                self._active_flyout.hide()
            except Exception:
                pass
        self._active_flyout = None
        self._focus_lost_timer.stop()

    def is_flyout_active(self, flyout: 'BaseFlyout') -> bool:
        return self._active_flyout is flyout and flyout.isVisible()

    def get_active_flyout(self) -> Optional['BaseFlyout']:
        if self._active_flyout is not None and self._active_flyout.isVisible():
            return self._active_flyout
        return None

    def _is_widget_in_flyout(self, widget: Optional[QWidget], flyout: Optional['BaseFlyout']) -> bool:
        if widget is None or flyout is None:
            return False

        if widget == flyout:
            return True

        parent = widget.parent()
        while parent is not None:
            if parent == flyout:
                return True
            parent = parent.parent()

        return False

    def _on_focus_changed(self, old: Optional[QWidget], new: Optional[QWidget]):
        if self._active_flyout is None or not self._active_flyout.isVisible():
            self._focus_lost_timer.stop()
            return

        has_focus = self._is_widget_in_flyout(new, self._active_flyout)

        if has_focus:

            self._focus_lost_timer.stop()
        else:

            if not self._focus_lost_timer.isActive():
                self._focus_lost_timer.start()

    def _on_focus_lost_timeout(self):
        if self._active_flyout is None or not self._active_flyout.isVisible():
            return

        app = QApplication.instance()
        if app:
            current_focus = app.focusWidget()

            if self._is_widget_in_flyout(current_focus, self._active_flyout):
                return

        try:
            self._active_flyout.hide()
        except Exception:
            pass
