from __future__ import annotations

import logging

logger = logging.getLogger("ImproveImgSLI")


def build_live_frame_snapshot(store):
    from tabs.registry import TabRegistry

    registry = TabRegistry()
    registry.discover()
    snapshot = registry.create_service("live_frame_snapshot", store)
    if snapshot is None:
        logger.debug(
            "Active tab %r does not provide live frame snapshots",
            getattr(registry, "_active_session_type", None),
        )
        return None
    return snapshot
