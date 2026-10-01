"""Re-export shim for the pyramid build coordinator.

The implementation moved to :mod:`engine.pyramid.coordinator` (the engine
owns the pyramid surface). This module is kept so existing
``from tabs._shared.pyramid import ...`` callers keep working unchanged
until every caller is migrated.
"""

from __future__ import annotations

from engine.pyramid.coordinator import (
    PYRAMID_START_PROGRESS,
    PyramidBuildCoordinator,
    _pyramid_build_loop,
)

__all__ = [
    "PYRAMID_START_PROGRESS",
    "PyramidBuildCoordinator",
    "_pyramid_build_loop",
]
