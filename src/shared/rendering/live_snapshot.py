from __future__ import annotations

import logging

logger = logging.getLogger("ImproveImgSLI")


def build_live_frame_snapshot(store):
    from tabs.registry import get_shared_tab_registry

    registry = get_shared_tab_registry()
    snapshot = registry.create_service("live_frame_snapshot", store)
    if snapshot is None:
        # Normal for session_picker / non-canvas tabs — silent degrade.
        return None
    return snapshot
