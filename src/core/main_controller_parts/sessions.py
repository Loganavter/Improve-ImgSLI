from __future__ import annotations

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
        return self.controller.session_manager.create_session(
            session_type,
            activate=activate,
            title=title,
            metadata=metadata,
        )

    def switch_workspace_session(self, session_id: str) -> bool:
        if not self.controller.session_manager:
            return False
        return self.controller.session_manager.switch_to_session(session_id)
