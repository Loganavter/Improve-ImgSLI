"""Plugin that registers the image_gallery session type.

This is the (separate, older) plugin/session-blueprint registration path —
``PluginCoordinator.create_session`` looks up session types here, not in
``TabRegistry`` (which only wires the tab's *page*/UI). Both must exist for a
tab to be creatable from the New Session picker; see ``tabs/multi_compare/plugin.py``
for the template this mirrors.
"""

from __future__ import annotations

from typing import Any

from core.plugin_system import Plugin, plugin
from core.plugin_system.interfaces import ISessionPlugin
from core.session_blueprints import SessionBlueprint, SessionSlotBlueprint


def _fresh_gallery_state_slot() -> dict:
    return {"folder": None}


@plugin(name="image_gallery", version="0.1", startup_tier="deferred")
class ImageGalleryPlugin(Plugin, ISessionPlugin):
    def __init__(self):
        super().__init__()
        self.store: Any | None = None
        self.event_bus: Any | None = None

    def initialize(self, context: Any) -> None:
        super().initialize(context)
        self.store = getattr(context, "store", None)
        self.event_bus = getattr(context, "event_bus", None)

    def get_session_blueprints(self) -> tuple[SessionBlueprint, ...]:
        return (
            SessionBlueprint(
                session_type="image_gallery",
                plugin_name="image_gallery",
                title="Image Gallery",
                state_slots=(
                    SessionSlotBlueprint(
                        name="image_gallery.state",
                        factory=_fresh_gallery_state_slot,
                    ),
                ),
            ),
        )
