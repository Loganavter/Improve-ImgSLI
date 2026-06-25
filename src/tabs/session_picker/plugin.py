"""Plugin that registers the new-session picker tab."""

from __future__ import annotations

from typing import Any

from core.plugin_system import Plugin, plugin
from core.plugin_system.interfaces import ISessionPlugin
from core.session_blueprints import SessionBlueprint


@plugin(name="session_picker", version="0.1")
class SessionPickerPlugin(Plugin, ISessionPlugin):
    def __init__(self):
        super().__init__()
        self.store: Any | None = None

    def initialize(self, context: Any) -> None:
        super().initialize(context)
        self.store = getattr(context, "store", None)

    def get_session_blueprints(self) -> tuple[SessionBlueprint, ...]:
        return (
            SessionBlueprint(
                session_type="session_picker",
                plugin_name="session_picker",
                title="New Tab",
                metadata_defaults={"transient": True},
            ),
        )
