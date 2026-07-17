"""Video / still snapshot frame rendering for image_compare.

Package layout:

- ``models`` — ``PreparedCanvasFrame``, cache entry shapes
- ``caches`` — ``FrameRenderCaches``
- ``geometry`` / ``images`` / ``store_rebuild`` — pure helpers
- ``prepare_hit`` / ``prepare_miss`` / ``prepare`` — prepare pipeline
- ``render`` — GPU composite of a prepared frame
- ``renderer`` — ``SnapshotFrameRenderer`` orchestrator
"""

from __future__ import annotations

from tabs.image_compare.services.video_snapshot_rendering.models import PreparedCanvasFrame
from tabs.image_compare.services.video_snapshot_rendering.renderer import (
    SnapshotFrameRenderer,
)

__all__ = ["PreparedCanvasFrame", "SnapshotFrameRenderer"]
