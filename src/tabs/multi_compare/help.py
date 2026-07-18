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
        "children": ["workspace.multi_compare.overview"],
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
}

_ALIASES = {
    "multi_compare": "workspace.multi_compare.overview",
    "multi_compare_overview": "workspace.multi_compare.overview",
    "mc_overview": "workspace.multi_compare.overview",
}


def resolve_help_icon(name: str) -> QIcon | None:
    for member in Icon:
        if member.value == name:
            icon = get_icon(member)
            if not icon.isNull():
                return icon
    return None


def contribute_help(registry) -> None:
    registry.contribute(
        attach_under="workspace",
        child_ids=("workspace.multi_compare",),
        nodes=_NODES,
        aliases=_ALIASES,
        body_root=_HELP_ROOT,
        asset_root=_HELP_ROOT,
        resolve_icon=resolve_help_icon,
    )
