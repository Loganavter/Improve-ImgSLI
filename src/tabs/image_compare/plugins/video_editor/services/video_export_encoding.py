"""Shim: FFmpeg helpers live in ``video_export.encoding``."""

from __future__ import annotations

from tabs.image_compare.plugins.video_editor.services.video_export.encoding import (
    FFmpegCommandBuilder,
    FFmpegProcessManager,
)

__all__ = [
    "FFmpegCommandBuilder",
    "FFmpegProcessManager",
]
