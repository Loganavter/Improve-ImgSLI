from __future__ import annotations

from typing import Any

from core.plugin_coordinator import PluginCoordinator
from core.session_blueprints import SessionBlueprint
from core.store import Store
from domain.workspace import WorkspaceSession

class SessionManager:
    def __init__(self, store: Store, plugin_coordinator: PluginCoordinator):
        self.store = store
        self.plugin_coordinator = plugin_coordinator

    def list_sessions(self) -> tuple[WorkspaceSession, ...]:
        return self.store.list_workspace_sessions()

    def get_active_session(self) -> WorkspaceSession | None:
        return self.store.get_active_workspace_session()

    def get_session(self, session_id: str) -> WorkspaceSession | None:
        return self.store.get_workspace_session(session_id)

    def switch_to_session(self, session_id: str) -> bool:
        return self.store.switch_workspace_session(session_id)

    def rename_session(self, session_id: str, title: str) -> bool:
        return self.store.rename_workspace_session(session_id, title)

    def list_session_types(self) -> tuple[str, ...]:
        return tuple(
            blueprint.session_type
            for blueprint in self.plugin_coordinator.list_session_blueprints()
        )

    def list_session_blueprints(self) -> tuple[SessionBlueprint, ...]:
        return self.plugin_coordinator.list_session_blueprints()

    def get_session_blueprint(self, session_type: str) -> SessionBlueprint | None:
        return self.plugin_coordinator.get_session_blueprint(session_type)

    def create_session(
        self,
        session_type: str,
        *,
        activate: bool = True,
        title: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> WorkspaceSession:
        session = self.plugin_coordinator.create_session(
            self.store,
            session_type,
            activate=activate,
            title=title,
        )
        if metadata:
            for key, value in metadata.items():
                self.store.set_session_metadata(
                    key,
                    value,
                    session_id=session.id,
                    emit_scope=None,
                )
        if metadata:
            self.store.emit_state_change("workspace")
        return session

    def ensure_session_type(self, session_type: str) -> SessionBlueprint:
        blueprint = self.get_session_blueprint(session_type)
        if blueprint is None:
            raise ValueError(f"Session type '{session_type}' is not registered")
        return blueprint
