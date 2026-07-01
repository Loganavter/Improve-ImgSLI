from __future__ import annotations


def build_live_frame_snapshot(store):
    from tabs.registry import TabRegistry

    registry = TabRegistry()
    registry.discover()
    snapshot = registry.create_service("live_frame_snapshot", store)
    if snapshot is None:
        raise RuntimeError("Active tab does not provide live frame snapshots")
    return snapshot
