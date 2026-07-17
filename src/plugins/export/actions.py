"""Temporary Find Action catalog for the still-image Export dialog chrome."""

from __future__ import annotations

from plugins.export.search import EXPORT_DIALOG_SEARCH
from ui.actions.dialog_contribute import (
    contribute_dialog_search_actions,
    withdraw_dialog_search_actions,
)
from ui.actions.registry import ActionRegistry

OWNER = "image_compare"
PREFIX = "image_compare.export_dialog."
_BC_EXPORT = "image_compare.action.breadcrumb.export"
_HELP = "export"


def contribute_export_dialog_actions(
    dialog,
    *,
    registry: ActionRegistry | None = None,
) -> None:
    """Register dialog chrome while the Export dialog is open."""
    contribute_dialog_search_actions(
        dialog,
        index=EXPORT_DIALOG_SEARCH,
        prefix=PREFIX,
        owner_tab=OWNER,
        topic="export",
        breadcrumb=(_BC_EXPORT,),
        help_page=_HELP,
        registry=registry,
    )


def withdraw_export_dialog_actions(
    *,
    registry: ActionRegistry | None = None,
) -> None:
    withdraw_dialog_search_actions(PREFIX, registry=registry)
