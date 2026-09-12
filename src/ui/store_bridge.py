from PySide6.QtCore import QObject, Signal

from core.store import Store

class QtStoreBridge(QObject):

    state_changed = Signal(str)

    def __init__(self, store: Store, parent=None):
        super().__init__(parent)
        store.on_change(self._on_store_changed)

        store.state_changed = self.state_changed

    def _on_store_changed(self, scope: str) -> None:
        self.state_changed.emit(scope)
