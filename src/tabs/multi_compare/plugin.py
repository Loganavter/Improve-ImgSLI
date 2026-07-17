"""Plugin that registers the multi_compare session type."""

from __future__ import annotations

from typing import Any

from core.plugin_system import Plugin, plugin
from core.plugin_system.interfaces import ISessionPlugin
from core.session_blueprints import SessionBlueprint, SessionSlotBlueprint


@plugin(name="multi_compare", version="0.1", startup_tier="deferred")
class MultiComparePlugin(Plugin, ISessionPlugin):
    def __init__(self):
        super().__init__()
        self.store: Any | None = None
        self.event_bus: Any | None = None

    def initialize(self, context: Any) -> None:
        super().initialize(context)
        self.store = getattr(context, "store", None)
        self.event_bus = getattr(context, "event_bus", None)

    def get_session_blueprints(self) -> tuple[SessionBlueprint, ...]:
        from tabs.multi_compare.tab import _fresh_default_state

        return (
            SessionBlueprint(
                session_type="multi_compare",
                plugin_name="multi_compare",
                title="Multi Compare",
                state_slots=(
                    SessionSlotBlueprint(
                        name="multi_compare.state",
                        factory=_fresh_default_state,
                    ),
                ),
            ),
        )

    def get_ui_components(self) -> dict[str, Any]:
        return {}
