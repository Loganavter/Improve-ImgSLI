import logging
from typing import Callable, List

from domain.workspace import WorkspaceState
from core.store_document import DocumentModel, ImageItem
from core.store_settings import SettingsState, WorkerStoreSnapshot
from core.store_operations import StoreOperationsMixin
from core.store_viewport import (
    MagnifierModel,
    RenderConfig,
    SessionData,
    ViewState,
    ViewportState,
)
from core.store_workspace import WorkspaceStoreMixin

logger = logging.getLogger("ImproveImgSLI")

__all__ = [
    "DocumentModel",
    "ImageItem",
    "MagnifierModel",
    "RenderConfig",
    "SessionData",
    "SettingsState",
    "Store",
    "ViewState",
    "ViewportState",
    "WorkerStoreSnapshot",
]

class Store(WorkspaceStoreMixin, StoreOperationsMixin):
    def __init__(self):
        self._change_callbacks: List[Callable[[str], None]] = []
        self.state_changed = None
        self.workspace = WorkspaceState()
        self.document = DocumentModel()
        self.viewport = ViewportState()
        self.settings = SettingsState()
        self.recorder = None
        self._dispatcher = None
        self.create_workspace_session(activate=True)

    def on_change(self, callback: Callable[[str], None]) -> None:
        self._change_callbacks.append(callback)

    def set_dispatcher(self, dispatcher):
        self._dispatcher = dispatcher

    def get_dispatcher(self):
        return self._dispatcher

    def set_recorder(self, recorder):
        self.recorder = recorder

    def emit_state_change(self, scope: str = "viewport"):
        for cb in self._change_callbacks:
            cb(scope)

    def _build_worker_snapshot(self, viewport: ViewportState, document: DocumentModel):
        return WorkerStoreSnapshot(
            viewport, self.settings.freeze_for_export(), document
        )
