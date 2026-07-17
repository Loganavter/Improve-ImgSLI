"""Shim: image repository lives in ``video_export.images``."""

from __future__ import annotations

from tabs.image_compare.plugins.video_editor.services.video_export.images import (
    VideoExportImageRepository,
)

__all__ = ["VideoExportImageRepository"]
