from __future__ import annotations

from core.events import (
    WorkspaceSessionActivatedEvent,
    WorkspaceSessionClosedEvent,
    WorkspaceSessionCreatedEvent,
)


class WorkspaceSessionActions:
    def __init__(self, controller):
        self.controller = controller

    def list_session_blueprints(self):
        if not self.controller.session_manager:
            return ()
        return self.controller.session_manager.list_session_blueprints()

    def create_workspace_session(
        self,
        session_type: str,
        *,
        activate: bool = True,
        title: str | None = None,
        metadata: dict | None = None,
    ):
        if not self.controller.session_manager:
            raise RuntimeError("SessionManager is not available")
        # Session picker may offer deferred types before their plugins load.
        if self.controller.session_manager.get_session_blueprint(session_type) is None:
            context = getattr(self.controller, "context", None)
            if context is not None:
                context.ensure_deferred_plugins_loaded()
            from tabs.registry import TabRegistry

            TabRegistry().discover(tier="deferred")
        previous = self.controller.session_manager.get_active_session()
        previous_id = previous.id if previous is not None else None
        session = self.controller.session_manager.create_session(
            session_type,
            activate=activate,
            title=title,
            metadata=metadata,
        )
        self._emit(
            WorkspaceSessionCreatedEvent(
                session_id=session.id, session_type=session.session_type
            )
        )
        if activate:
            self._emit_activated(session.id, session.session_type, previous_id)
        return session

    def switch_workspace_session(self, session_id: str) -> bool:
        if not self.controller.session_manager:
            return False
        previous = self.controller.session_manager.get_active_session()
        previous_id = previous.id if previous is not None else None
        if not self.controller.session_manager.switch_to_session(session_id):
            return False
        active = self.controller.session_manager.get_active_session()
        if active is not None:
            self._emit_activated(active.id, active.session_type, previous_id)
        return True

    def close_workspace_session(self, session_id: str) -> bool:
        if not self.controller.session_manager:
            return False
        session = self.controller.session_manager.get_session(session_id)
        session_type = session.session_type if session is not None else None
        was_active = (
            session is not None
            and self.controller.session_manager.get_active_session() is not None
            and self.controller.session_manager.get_active_session().id == session_id
        )
        closed = self.controller.session_manager.close_session(session_id)
        if closed and session_type is not None:
            self._emit(
                WorkspaceSessionClosedEvent(
                    session_id=session_id, session_type=session_type
                )
            )
            if was_active:
                active = self.controller.session_manager.get_active_session()
                if active is not None:
                    self._emit_activated(
                        active.id, active.session_type, session_id
                    )
        return closed

    def duplicate_workspace_session(
        self,
        source_session_id: str,
        *,
        activate: bool = True,
        tab_registry=None,
    ):
        if not self.controller.session_manager:
            raise RuntimeError("SessionManager is not available")
        source = self.controller.session_manager.get_session(source_session_id)
        if source is None:
            raise ValueError(f"Unknown workspace session: {source_session_id}")
        if tab_registry is None:
            raise ValueError("tab_registry is required for duplicate_workspace_session")
        snapshot = tab_registry.duplicate_session(
            source.session_type, source_session_id
        )
        if snapshot is None:
            raise ValueError(
                f"Session type {source.session_type!r} does not support duplication"
            )
        session = self.create_workspace_session(
            source.session_type,
            activate=False,
            title=f"{source.title} (copy)" if source.title else None,
        )
        tab_registry.deserialize_session(
            source.session_type, session.id, snapshot
        )
        tab_registry.rehydrate_session(source.session_type, session.id)
        if activate:
            self.switch_workspace_session(session.id)
        return session

    def _emit_activated(
        self,
        session_id: str,
        session_type: str,
        previous_session_id: str | None,
    ) -> None:
        if previous_session_id == session_id:
            return
        self._emit(
            WorkspaceSessionActivatedEvent(
                session_id=session_id,
                session_type=session_type,
                previous_session_id=previous_session_id,
            )
        )

    def _emit(self, event) -> None:
        event_bus = getattr(self.controller, "event_bus", None)
        if event_bus is not None:
            event_bus.emit(event)
