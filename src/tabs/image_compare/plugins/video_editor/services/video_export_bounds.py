"""Shim: bounds analyzer lives in ``video_export.bounds``."""

from __future__ import annotations

from tabs.image_compare.plugins.video_editor.services.video_export.bounds import (
    CanvasBoundsAnalyzer,
)

__all__ = ["CanvasBoundsAnalyzer"]
