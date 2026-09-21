"""Temporary Find Action catalog for the still-image Export dialog chrome."""

from __future__ import annotations

from plugins.export.search import EXPORT_DIALOG_SEARCH
from ui.actions.dialog_contribute import (
    contribute_dialog_search_actions,
    withdraw_dialog_search_actions,
)
from ui.actions.registry import ActionRegistry

_HELP = "export"

#: Stable Find Action id prefix for the Export dialog chrome. Deliberately
#: NOT owner-tab-scoped: the dialog is one chrome surface, and an
#: active-tab-derived prefix (``<tab>.export_dialog.…``) would register a
#: different id set depending on which tab opened it — stale ids across
#: tabs and palette duplicates. Tab attribution travels in the
#: ``owner_tab`` metadata field instead (see ``contribute_dialog_…``).
_EXPORT_DIALOG_PREFIX = "export_dialog."


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
    prefix = _EXPORT_DIALOG_PREFIX
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
    # Stable prefix needs no owner (param kept for signature compatibility).
    del owner_tab
    withdraw_dialog_search_actions(_EXPORT_DIALOG_PREFIX, registry=registry)
