from __future__ import annotations

from core.events import WorkspaceSessionClosedEvent, WorkspaceSessionCreatedEvent

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
        return session

    def switch_workspace_session(self, session_id: str) -> bool:
        if not self.controller.session_manager:
            return False
        return self.controller.session_manager.switch_to_session(session_id)

    def close_workspace_session(self, session_id: str) -> bool:
        if not self.controller.session_manager:
            return False
        session = self.controller.session_manager.get_session(session_id)
        session_type = session.session_type if session is not None else None
        closed = self.controller.session_manager.close_session(session_id)
        if closed and session_type is not None:
            self._emit(
                WorkspaceSessionClosedEvent(
                    session_id=session_id, session_type=session_type
                )
            )
        return closed

    def _emit(self, event) -> None:
        event_bus = getattr(self.controller, "event_bus", None)
        if event_bus is not None:
            event_bus.emit(event)
