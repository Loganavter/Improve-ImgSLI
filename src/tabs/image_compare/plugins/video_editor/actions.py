"""Temporary Find Action catalog for the Video Editor dialog chrome."""

from __future__ import annotations

from ui.actions.dialog_contribute import (
    contribute_dialog_search_actions,
    withdraw_dialog_search_actions,
)
from ui.actions.registry import ActionRegistry
from tabs.image_compare.plugins.video_editor.search import (
    VIDEO_EDITOR_SEARCH,
    VIDEO_EDITOR_SHORTCUTS,
)

OWNER = "image_compare"
PREFIX = "image_compare.video_editor."
_BC_VIDEO = "image_compare.action.breadcrumb.video"
_BC_EDITOR = "image_compare.action.video_editor"
_HELP = "video"


def contribute_video_editor_actions(
    dialog,
    *,
    registry: ActionRegistry | None = None,
) -> None:
    """Register dialog chrome while the Video Editor window is open."""
    contribute_dialog_search_actions(
        dialog,
        index=VIDEO_EDITOR_SEARCH,
        prefix=PREFIX,
        owner_tab=OWNER,
        topic="video",
        breadcrumb=(_BC_VIDEO, _BC_EDITOR),
        help_page=_HELP,
        registry=registry,
        shortcuts=VIDEO_EDITOR_SHORTCUTS,
    )


def withdraw_video_editor_actions(
    *,
    registry: ActionRegistry | None = None,
) -> None:
    withdraw_dialog_search_actions(PREFIX, registry=registry)
