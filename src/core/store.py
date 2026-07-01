import logging
from typing import Callable, List, Optional

from domain.workspace import WorkspaceState
from core.store_document import DocumentModel, ImageItem
from core.store_settings import SettingsState, WorkerStoreSnapshot
from core.store_operations import StoreOperationsMixin
from core.store_runtime_cache import ViewportRuntimeCache
from core.store_viewport import (
    GeometryState,
    ImageSessionState,
    InteractionState,
    RenderConfig,
    RenderCacheState,
    SessionData,
    ViewState,
    ViewportState,
)
from core.store_workspace import WorkspaceStoreMixin

logger = logging.getLogger("ImproveImgSLI")
INITIAL_WORKSPACE_SESSION_TYPE = "session_picker"

__all__ = [
    "DocumentModel",
    "GeometryState",
    "ImageItem",
    "ImageSessionState",
    "InteractionState",
    "RenderConfig",
    "RenderCacheState",
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
        self._pre_session_document: Optional[DocumentModel] = DocumentModel()
        self._pre_session_viewport: Optional[ViewportState] = ViewportState()
        self.settings = SettingsState()
        self.runtime_cache = ViewportRuntimeCache()
        self.recorder = None
        self._dispatcher = None
        self.create_workspace_session(
            session_type=INITIAL_WORKSPACE_SESSION_TYPE,
            activate=True,
        )

    @property
    def document(self) -> DocumentModel:
        session = self.get_active_workspace_session()
        if session is None:
            return self._pre_session_document
        return session.document

    @document.setter
    def document(self, value: DocumentModel) -> None:
        session = self.get_active_workspace_session()
        if session is None:
            self._pre_session_document = value
        else:
            session.document = value

    @property
    def viewport(self) -> ViewportState:
        session = self.get_active_workspace_session()
        if session is None:
            return self._pre_session_viewport
        return session.viewport

    @viewport.setter
    def viewport(self, value: ViewportState) -> None:
        session = self.get_active_workspace_session()
        if session is None:
            self._pre_session_viewport = value
        else:
            session.viewport = value

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

    def emit_viewport_change(self, subdomain: str | None = None) -> None:
        scope = "viewport"
        if subdomain:
            scope = f"viewport.{subdomain}"
        self.emit_state_change(scope)

    def _build_worker_snapshot(self, viewport: ViewportState, document: DocumentModel):
        return WorkerStoreSnapshot(
            viewport, self.settings.freeze_for_export(), document
        )
