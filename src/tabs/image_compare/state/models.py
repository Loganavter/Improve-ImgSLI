"""Compatibility re-export of session-state dataclasses.

The dataclasses live in :mod:`core.store_viewport` because
:class:`core.store_viewport.ViewportState` owns ``render_config`` and
``session_data`` as named slots — the full extraction into a tab-owned
``session_state_slot`` requires a fan-out across ~340 ``viewport.session_data``
/ ``viewport.render_config`` accesses across core/services/plugins and is
tracked as the remaining body of step 9 in the migration plan.

Until that fan-out lands, tab code keeps importing these types from this
module so the import direction (tab → core) is correct.
"""

from __future__ import annotations

from core.store_viewport import (
    ImageSessionState,
    RenderCacheState,
    RenderConfig,
    SessionData,
)

__all__ = [
    "ImageSessionState",
    "RenderCacheState",
    "RenderConfig",
    "SessionData",
]
