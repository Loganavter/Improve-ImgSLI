from __future__ import annotations

from typing import Any, Callable

from domain.workspace import WorkspaceSession

from core.store_document import DocumentModel
from core.store_viewport import ViewportState
from core.session_blueprints import SessionBlueprint

class WorkspaceStoreMixin:
    def get_workspace_session(self, session_id: str) -> WorkspaceSession | None:
        for session in self.workspace.sessions:
            if session.id == session_id:
                return session
        return None

    def list_workspace_sessions(self) -> tuple[WorkspaceSession, ...]:
        return tuple(self.workspace.sessions)

    def get_active_workspace_session(self) -> WorkspaceSession | None:
        active_id = self.workspace.active_session_id
        if not active_id:
            return None
        return self.get_workspace_session(active_id)

    def create_workspace_session(
        self,
        title: str | None = None,
        session_type: str = "image_compare",
        activate: bool = True,
        blueprint: SessionBlueprint | None = None,
    ) -> WorkspaceSession:
        session = WorkspaceSession(
            id=self.workspace.new_session_id(),
            title=title or self.workspace.next_default_title(session_type),
            session_type=session_type,
            document=DocumentModel(),
            viewport=ViewportState(),
        )
        if blueprint is not None:
            self._apply_session_blueprint(session, blueprint)
        self.workspace.sessions.append(session)
        if activate or not self.workspace.active_session_id:
            self._activate_workspace_session(session)
            self.emit_state_change("workspace")
            self.emit_state_change("document")
            self.emit_state_change("viewport")
        else:
            self.emit_state_change("workspace")
        return session

    def switch_workspace_session(self, session_id: str) -> bool:
        for session in self.workspace.sessions:
            if session.id == session_id:
                if session.id == self.workspace.active_session_id:
                    return False
                self._activate_workspace_session(session)
                self.emit_state_change("workspace")
                self.emit_state_change("document")
                self.emit_state_change("viewport")
                return True
        return False

    def rename_workspace_session(self, session_id: str, title: str) -> bool:
        normalized = title.strip()
        if not normalized:
            return False
        session = self.get_workspace_session(session_id)
        if session is not None:
            if session.title == normalized:
                return False
            session.title = normalized
            self.emit_state_change("workspace")
            return True
        return False

    def get_session_state_slot(
        self,
        slot_name: str,
        *,
        session_id: str | None = None,
        default: Any = None,
    ) -> Any:
        session = self._require_workspace_session(session_id)
        return session.state_slots.get(slot_name, default)

    def ensure_session_state_slot(
        self,
        slot_name: str,
        *,
        session_id: str | None = None,
        factory: Callable[[], Any] | None = None,
        default: Any = None,
        emit_change: bool = False,
    ) -> Any:
        session = self._require_workspace_session(session_id)
        if slot_name in session.state_slots:
            return session.state_slots[slot_name]

        value = factory() if factory is not None else default
        session.state_slots[slot_name] = value
        if emit_change:
            self.emit_state_change("workspace")
        return value

    def set_session_state_slot(
        self,
        slot_name: str,
        value: Any,
        *,
        session_id: str | None = None,
        emit_scope: str = "workspace",
    ) -> Any:
        session = self._require_workspace_session(session_id)
        session.state_slots[slot_name] = value
        if emit_scope:
            self.emit_state_change(emit_scope)
        return value

    def move_session_state_slot(
        self,
        slot_name: str,
        *,
        from_session_id: str,
        to_session_id: str,
        emit_scope: str = "workspace",
    ) -> Any:
        source = self._require_workspace_session(from_session_id)
        target = self._require_workspace_session(to_session_id)
        if source.id == target.id:
            return source.state_slots.get(slot_name)
        value = source.state_slots.pop(slot_name, None)
        if value is not None:
            target.state_slots[slot_name] = value
            if emit_scope:
                self.emit_state_change(emit_scope)
        return value

    def remove_session_state_slot(
        self,
        slot_name: str,
        *,
        session_id: str | None = None,
        emit_scope: str = "workspace",
    ) -> Any:
        session = self._require_workspace_session(session_id)
        value = session.state_slots.pop(slot_name, None)
        if value is not None and emit_scope:
            self.emit_state_change(emit_scope)
        return value

    def get_session_resource_namespace(
        self,
        namespace: str,
        *,
        session_id: str | None = None,
        create: bool = False,
    ) -> dict[str, Any] | None:
        session = self._require_workspace_session(session_id)
        if create:
            return session.resources.setdefault(namespace, {})
        return session.resources.get(namespace)

    def get_session_resource(
        self,
        namespace: str,
        key: str,
        *,
        session_id: str | None = None,
        default: Any = None,
    ) -> Any:
        resources = self.get_session_resource_namespace(
            namespace, session_id=session_id, create=False
        )
        if resources is None:
            return default
        return resources.get(key, default)

    def set_session_resource(
        self,
        namespace: str,
        key: str,
        value: Any,
        *,
        session_id: str | None = None,
        emit_scope: str | None = None,
    ) -> Any:
        resources = self.get_session_resource_namespace(
            namespace, session_id=session_id, create=True
        )
        resources[key] = value
        if emit_scope:
            self.emit_state_change(emit_scope)
        return value

    def pop_session_resource(
        self,
        namespace: str,
        key: str,
        *,
        session_id: str | None = None,
        emit_scope: str | None = None,
    ) -> Any:
        resources = self.get_session_resource_namespace(
            namespace, session_id=session_id, create=False
        )
        if resources is None:
            return None
        value = resources.pop(key, None)
        if emit_scope and value is not None:
            self.emit_state_change(emit_scope)
        if not resources:
            self.clear_session_resource_namespace(
                namespace, session_id=session_id, emit_scope=None
            )
        return value

    def clear_session_resource_namespace(
        self,
        namespace: str,
        *,
        session_id: str | None = None,
        emit_scope: str | None = None,
    ) -> dict[str, Any] | None:
        session = self._require_workspace_session(session_id)
        removed = session.resources.pop(namespace, None)
        if emit_scope and removed is not None:
            self.emit_state_change(emit_scope)
        return removed

    def move_session_resource_namespace(
        self,
        namespace: str,
        *,
        from_session_id: str,
        to_session_id: str,
        emit_scope: str = "workspace",
        replace: bool = True,
    ) -> dict[str, Any] | None:
        source = self._require_workspace_session(from_session_id)
        target = self._require_workspace_session(to_session_id)
        if source.id == target.id:
            return source.resources.get(namespace)

        payload = source.resources.pop(namespace, None)
        if payload is None:
            return None

        if replace or namespace not in target.resources:
            target.resources[namespace] = payload
        else:
            target.resources[namespace].update(payload)

        if emit_scope:
            self.emit_state_change(emit_scope)
        return target.resources[namespace]

    def iter_session_resources(
        self,
        *,
        session_id: str | None = None,
    ) -> tuple[tuple[str, dict[str, Any]], ...]:
        session = self._require_workspace_session(session_id)
        return tuple(session.resources.items())

    def get_session_metadata(
        self,
        key: str,
        *,
        session_id: str | None = None,
        default: Any = None,
    ) -> Any:
        session = self._require_workspace_session(session_id)
        return session.metadata.get(key, default)

    def set_session_metadata(
        self,
        key: str,
        value: Any,
        *,
        session_id: str | None = None,
        emit_scope: str = "workspace",
    ) -> Any:
        session = self._require_workspace_session(session_id)
        session.metadata[key] = value
        if emit_scope:
            self.emit_state_change(emit_scope)
        return value

    def remove_session_metadata(
        self,
        key: str,
        *,
        session_id: str | None = None,
        emit_scope: str = "workspace",
    ) -> Any:
        session = self._require_workspace_session(session_id)
        value = session.metadata.pop(key, None)
        if value is not None and emit_scope:
            self.emit_state_change(emit_scope)
        return value

    def _activate_workspace_session(self, session: WorkspaceSession) -> None:
        self.workspace.active_session_id = session.id
        self.document = session.document
        self.viewport = session.viewport

    def _apply_session_blueprint(
        self, session: WorkspaceSession, blueprint: SessionBlueprint
    ) -> None:
        for slot in blueprint.state_slots:
            session.state_slots[slot.name] = (
                slot.factory() if slot.factory is not None else slot.default
            )

        for resource in blueprint.resource_namespaces:
            session.resources[resource.namespace] = dict(resource.entries)

        if blueprint.metadata_defaults:
            session.metadata.update(dict(blueprint.metadata_defaults))

    def _require_workspace_session(
        self, session_id: str | None = None
    ) -> WorkspaceSession:
        session = (
            self.get_workspace_session(session_id)
            if session_id is not None
            else self.get_active_workspace_session()
        )
        if session is None:
            raise ValueError("Workspace session is not available")
        return session
