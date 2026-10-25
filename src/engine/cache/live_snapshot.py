from __future__ import annotations

import logging
from core.log_names import APP_LOGGER_NAME

logger = logging.getLogger(APP_LOGGER_NAME)


def build_live_frame_snapshot(store):
    from tabs.registry import get_shared_tab_registry

    registry = get_shared_tab_registry()
    snapshot = registry.create_service("live_frame_snapshot", store)
    if snapshot is None:
        # Normal for tabs without canvas — silent degrade.  # ALLOWED: generic, no tab name
        return None
    return snapshot
