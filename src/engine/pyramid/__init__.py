"""Engine-owned pyramid build coordinator.

The build orchestration (worker lifecycle + toast-slot routing) moved here
from the tab layer so the engine owns the whole pyramid surface. Kept as a
public re-export so engine consumers have a single import root.
"""

from .coordinator import (
    PYRAMID_START_PROGRESS,
    PyramidBuildCoordinator,
    _pyramid_build_loop,
)

__all__ = [
    "PYRAMID_START_PROGRESS",
    "PyramidBuildCoordinator",
    "_pyramid_build_loop",
]
