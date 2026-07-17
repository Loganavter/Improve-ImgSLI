"""Video export pipeline: models, bounds, encoding, images, render loop, service."""

from __future__ import annotations

from typing import TYPE_CHECKING

from tabs.image_compare.plugins.video_editor.services.video_export.bounds import (
    CanvasBoundsAnalyzer,
)
from tabs.image_compare.plugins.video_editor.services.video_export.encoding import (
    FFmpegCommandBuilder,
    FFmpegProcessManager,
)
from tabs.image_compare.plugins.video_editor.services.video_export.images import (
    VideoExportImageRepository,
)
from tabs.image_compare.plugins.video_editor.services.video_export.models import (
    FrameTimingStats,
    GlobalCanvasBounds,
    RenderedFrame,
    VideoExportJob,
    VideoRenderRequest,
    unique_video_path,
)

if TYPE_CHECKING:
    from tabs.image_compare.plugins.video_editor.services.video_export.render_loop import (
        VideoRenderLoop,
    )
    from tabs.image_compare.plugins.video_editor.services.video_export.service import (
        VIDEO_EDITOR_AUTO_CROP,
        VideoExporterService,
    )

__all__ = [
    "VIDEO_EDITOR_AUTO_CROP",
    "CanvasBoundsAnalyzer",
    "FFmpegCommandBuilder",
    "FFmpegProcessManager",
    "FrameTimingStats",
    "GlobalCanvasBounds",
    "RenderedFrame",
    "VideoExportImageRepository",
    "VideoExportJob",
    "VideoExporterService",
    "VideoRenderLoop",
    "VideoRenderRequest",
    "unique_video_path",
]


def __getattr__(name: str):
    # Lazy: service/render_loop pull SnapshotFrameRenderer and must not load
    # when callers only need models (avoids circular import via shims).
    if name == "VideoRenderLoop":
        from tabs.image_compare.plugins.video_editor.services.video_export.render_loop import (
            VideoRenderLoop,
        )

        return VideoRenderLoop
    if name == "VideoExporterService":
        from tabs.image_compare.plugins.video_editor.services.video_export.service import (
            VideoExporterService,
        )

        return VideoExporterService
    if name == "VIDEO_EDITOR_AUTO_CROP":
        from tabs.image_compare.plugins.video_editor.services.video_export.service import (
            VIDEO_EDITOR_AUTO_CROP,
        )

        return VIDEO_EDITOR_AUTO_CROP
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
