import logging
from contextlib import contextmanager
from typing import Any, Callable, List, Optional

from domain.workspace import WorkspaceState
from core.store_settings import SettingsState, WorkerStoreSnapshot
from core.store_operations import StoreOperationsMixin
from core.store_runtime_cache import ViewportRuntimeCache
from core.store_viewport import (
    GeometryState,
    InteractionState,
    RenderConfig,
    SessionData,
    ViewState,
    ViewportState,
)
from core.store_workspace import WorkspaceStoreMixin

logger = logging.getLogger("ImproveImgSLI")
INITIAL_WORKSPACE_SESSION_TYPE = "session_picker"

__all__ = [
    "GeometryState",
    "InteractionState",
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
        self._pre_session_document: Optional[Any] = None
        self._pre_session_viewport: Optional[ViewportState] = ViewportState()
        self.settings = SettingsState()
        self.runtime_cache = ViewportRuntimeCache()
        self.recorder = None
        self._dispatcher = None
        self._change_batch_depth = 0
        self._change_batch_scopes: list[str] = []
        self.create_workspace_session(
            session_type=INITIAL_WORKSPACE_SESSION_TYPE,
            activate=True,
        )

    @property
    def document(self) -> Any:
        session = self.get_active_workspace_session()
        if session is None:
            return self._pre_session_document
        return session.document

    @document.setter
    def document(self, value: Any) -> None:
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
        if self._change_batch_depth > 0:
            if scope not in self._change_batch_scopes:
                self._change_batch_scopes.append(scope)
            return
        for cb in self._change_callbacks:
            cb(scope)

    @contextmanager
    def batch_changes(self):
        """Coalesce change emissions inside the block into a single flush at exit.

        Several operations are semantically one user-visible transition but
        internally mutate the store in steps (e.g. ``create_workspace_session``
        + ``close_workspace_session`` when the session picker is replaced by a
        new session). Emitting per step makes the workspace UI sync to each
        intermediate state — and the adaptive tab strip legitimately holds
        *two* tabs between those steps, so an intermediate frame shows two tabs
        before the replacement lands. Batching defers every emission until the
        block ends, so listeners only ever see the coherent final state.
        Reads inside the block still see the mutated store immediately; only
        the change notifications are deferred. Scopes are flushed once each, in
        first-emitted order.
        """
        self._change_batch_depth += 1
        try:
            yield
        finally:
            self._change_batch_depth -= 1
            if self._change_batch_depth == 0:
                scopes = list(self._change_batch_scopes)
                self._change_batch_scopes = []
                for scope in scopes:
                    self.emit_state_change(scope)

    def emit_viewport_change(self, subdomain: str | None = None) -> None:
        scope = "viewport"
        if subdomain:
            scope = f"viewport.{subdomain}"
        self.emit_state_change(scope)

    def build_worker_snapshot(self, viewport: ViewportState, document: Any):
        return WorkerStoreSnapshot(
            viewport, self.settings.freeze_for_export(), document
        )