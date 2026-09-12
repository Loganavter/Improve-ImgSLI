"""Temporary Find Action catalog for the still-image Export dialog chrome."""

from __future__ import annotations

from plugins.export.search import EXPORT_DIALOG_SEARCH
from ui.actions.dialog_contribute import (
    contribute_dialog_search_actions,
    withdraw_dialog_search_actions,
)
from ui.actions.registry import ActionRegistry

_HELP = "export"


def _export_dialog_owner_tab() -> str:
    from tabs.registry import TabRegistry

    tab = TabRegistry().get_active_tab()
    return tab.session_type if tab is not None else ""


def contribute_export_dialog_actions(
    dialog,
    *,
    registry: ActionRegistry | None = None,
    owner_tab: str | None = None,
) -> None:
    """Register dialog chrome while the Export dialog is open."""
    owner = owner_tab or _export_dialog_owner_tab()
    prefix = f"{owner}.export_dialog." if owner else "export_dialog."
    breadcrumb = (f"{owner}.action.breadcrumb.export",) if owner else ("action.breadcrumb.export",)
    contribute_dialog_search_actions(
        dialog,
        index=EXPORT_DIALOG_SEARCH,
        prefix=prefix,
        owner_tab=owner or None,
        topic="export",
        breadcrumb=breadcrumb,
        help_page=_HELP,
        registry=registry,
    )


def withdraw_export_dialog_actions(
    *,
    registry: ActionRegistry | None = None,
    owner_tab: str | None = None,
) -> None:
    owner = owner_tab or _export_dialog_owner_tab()
    prefix = f"{owner}.export_dialog." if owner else "export_dialog."
    withdraw_dialog_search_actions(prefix, registry=registry)
