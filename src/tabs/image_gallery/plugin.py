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
from tabs.image_gallery.bootstrap_reducers import GALLERY_SLOT_NAME
from tabs.image_gallery.state.models import fresh_gallery_slot_state


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
        # THE composition point of ADR 009's analysis backends: the two adapters
        # are registered here, once per process — ``initialize`` runs before any
        # controller exists and is never repeated (unlike ``create_page``, which
        # rebuilds the controller after a ``dispose``). Registration is
        # idempotent by ``backend_id``; the registry stays strict about a second
        # ADAPTER claiming an id or a cache namespace.
        from tabs.image_gallery.backends.composition import (
            register_gallery_backends,
        )

        register_gallery_backends()
        from tabs.image_gallery.bootstrap_reducers import (
            register_gallery_reducers,
        )

        register_gallery_reducers()

    def get_session_blueprints(self) -> tuple[SessionBlueprint, ...]:
        return (
            SessionBlueprint(
                session_type="image_gallery",
                plugin_name="image_gallery",
                title="Image Gallery",
                state_slots=(
                    SessionSlotBlueprint(
                        name=GALLERY_SLOT_NAME,
                        factory=fresh_gallery_slot_state,
                    ),
                ),
            ),
        )
