"""Forwarder — real logic lives in use_cases/initialization.py (thin owner)."""

from tabs.image_compare.plugins.video_editor.use_cases.initialization import (
    initialize_editor_from_snapshots,
)

__all__ = ["initialize_editor_from_snapshots"]
