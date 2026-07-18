"""Image Compare help subtree contributed into the host Help tree."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QIcon

from tabs.image_compare.icons import Icon, get_icon

_HELP_ROOT = Path(__file__).resolve().parent / "resources" / "help"

_NODES = {
    "workspace.image_compare": {
        "kind": "hub",
        "title_key": "workspace.session_types.image_compare",
        "description_key": "image_compare.help.hub.desc",
        "title": "Image Compare",
        "description": "Two-image compare, magnifier, export",
        "icon": "vertical_split.svg",
        "children": [
            "workspace.image_compare.comparison",
            "workspace.image_compare.magnifier",
            "workspace.image_compare.export",
            "workspace.image_compare.video",
        ],
    },
    "workspace.image_compare.comparison": {
        "kind": "page",
        "title_key": "image_compare.help.page.comparison.title",
        "description_key": "image_compare.help.page.comparison.desc",
        "title": "Comparison",
        "description": "Split line, labels, difference modes",
        "icon": "divider_visible.svg",
        "body": "comparison.md",
    },
    "workspace.image_compare.magnifier": {
        "kind": "page",
        "title_key": "image_compare.help.page.magnifier.title",
        "description_key": "image_compare.help.page.magnifier.desc",
        "title": "Magnifier",
        "description": "Capture area, freeze, combined mode",
        "icon": "magnifier.svg",
        "body": "magnifier.md",
    },
    "workspace.image_compare.export": {
        "kind": "page",
        "title_key": "image_compare.help.page.export.title",
        "description_key": "image_compare.help.page.export.desc",
        "title": "Export",
        "description": "Stills and quick-save",
        "icon": "save_icon.svg",
        "body": "export.md",
    },
    "workspace.image_compare.video": {
        "kind": "page",
        "title_key": "image_compare.help.page.video.title",
        "description_key": "image_compare.help.page.video.desc",
        "title": "Video Editor",
        "description": "Record, trim, encode",
        "icon": "play.svg",
        "body": "video.md",
    },
}

_ALIASES = {
    "comparison": "workspace.image_compare.comparison",
    "magnifier": "workspace.image_compare.magnifier",
    "export": "workspace.image_compare.export",
    "video": "workspace.image_compare.video",
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
        child_ids=("workspace.image_compare",),
        nodes=_NODES,
        aliases=_ALIASES,
        body_root=_HELP_ROOT,
        asset_root=_HELP_ROOT,
        resolve_icon=resolve_help_icon,
    )
