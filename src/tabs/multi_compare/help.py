"""Multi Compare help subtree contributed into the host Help tree."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QIcon

from tabs.multi_compare.icons import Icon, get_icon

_HELP_ROOT = Path(__file__).resolve().parent / "resources" / "help"

_NODES = {
    "workspace.multi_compare": {
        "kind": "hub",
        "title_key": "workspace.session_types.multi_compare",
        "description_key": "multi_compare.help.hub.desc",
        "title": "Multi Compare",
        "description": "Many-image layouts",
        "icon": "grid.svg",
        "children": [
            "workspace.multi_compare.overview",
            "workspace.multi_compare.layouts",
            "workspace.multi_compare.viewing",
            "workspace.multi_compare.export",
        ],
    },
    "workspace.multi_compare.overview": {
        "kind": "page",
        "title_key": "multi_compare.help.page.overview.title",
        "description_key": "multi_compare.help.page.overview.desc",
        "title": "Multi Compare Overview",
        "description": "Layouts and drop zones",
        "icon": "grid.svg",
        "body": "overview.md",
    },
    "workspace.multi_compare.layouts": {
        "kind": "page",
        "title_key": "multi_compare.help.page.layouts.title",
        "description_key": "multi_compare.help.page.layouts.desc",
        "title": "Multi Compare Layouts",
        "description": "Cells, gap splits, dividers, slot actions",
        "icon": "grid.svg",
        "body": "layouts.md",
    },
    "workspace.multi_compare.viewing": {
        "kind": "page",
        "title_key": "multi_compare.help.page.viewing.title",
        "description_key": "multi_compare.help.page.viewing.desc",
        "title": "Multi Compare Viewing",
        "description": "Focus mode, zoom and pan, labels, crop",
        "icon": "grid.svg",
        "body": "viewing.md",
    },
    "workspace.multi_compare.export": {
        "kind": "page",
        "title_key": "multi_compare.help.page.export.title",
        "description_key": "multi_compare.help.page.export.desc",
        "title": "Multi Compare Export",
        "description": "Quick save, save dialog, sessions",
        "icon": "grid.svg",
        "body": "export.md",
    },
}

_ALIASES = {
    "multi_compare": "workspace.multi_compare.overview",
    "multi_compare_overview": "workspace.multi_compare.overview",
    "mc_overview": "workspace.multi_compare.overview",
    "mc_layouts": "workspace.multi_compare.layouts",
    "mc_viewing": "workspace.multi_compare.viewing",
    "mc_export": "workspace.multi_compare.export",
}


def resolve_help_icon(name: str) -> QIcon | None:
    for member in Icon:
        if member.value == name:
            icon = get_icon(member)
            if not icon.isNull():
                return icon
    return None


def build_help_contribution():  # type: ignore[no-untyped-def]
    """Return typed ``HelpContribution`` for ``multi_compare`` (isolated)."""
    from plugins.help.contribution import HelpContribution

    return HelpContribution(
        owner_tab="multi_compare",
        attach_under="workspace",
        child_ids=("workspace.multi_compare",),
        nodes=dict(_NODES),
        aliases=dict(_ALIASES),
        body_root=_HELP_ROOT,
        asset_root=_HELP_ROOT,
        resolve_icon=resolve_help_icon,
    )


def contribute_help(registry) -> None:  # deprecated shim
    """Deprecated: mutates ``registry`` — prefer ``build_help_contribution``."""
    contrib = build_help_contribution()
    registry.contribute(
        attach_under=contrib.attach_under,
        child_ids=contrib.child_ids,
        nodes=dict(contrib.nodes),
        aliases=dict(contrib.aliases),
        body_root=contrib.body_root,
        asset_root=contrib.asset_root,
        resolve_icon=contrib.resolve_icon,
    )
