"""Video editor dialog shell and satellites."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tabs.image_compare.plugins.video_editor.dialog.shell import VideoEditorDialog

__all__ = ["VideoEditorDialog"]


def __getattr__(name: str):
    if name == "VideoEditorDialog":
        from tabs.image_compare.plugins.video_editor.dialog.shell import VideoEditorDialog

        return VideoEditorDialog
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
