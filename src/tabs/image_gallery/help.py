"""Image Gallery help subtree contributed into the host Help tree."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QIcon

from tabs.image_gallery.icons import Icon, get_icon

_HELP_ROOT = Path(__file__).resolve().parent / "resources" / "help"

_NODES = {
    "workspace.image_gallery": {
        "kind": "hub",
        "title_key": "image_gallery.help.hub.title",
        "description_key": "image_gallery.help.hub.desc",
        "title": "Image Gallery",
        "description": "Browse, triage, and review image folders",
        "icon": "gallery.svg",
        "children": [
            "workspace.image_gallery.overview",
            "workspace.image_gallery.triage",
            "workspace.image_gallery.quality",
            "workspace.image_gallery.ask_ai",
        ],
    },
    "workspace.image_gallery.overview": {
        "kind": "page",
        "title_key": "image_gallery.help.page.overview.title",
        "description_key": "image_gallery.help.page.overview.desc",
        "title": "Gallery Overview",
        "description": "Folders, series, grid, and compare",
        "icon": "gallery.svg",
        "body": "overview.md",
    },
    "workspace.image_gallery.triage": {
        "kind": "page",
        "title_key": "image_gallery.help.page.triage.title",
        "description_key": "image_gallery.help.page.triage.desc",
        "title": "Triage and Review",
        "description": "Keep best, reject, and clean review",
        "icon": "star.svg",
        "body": "triage.md",
    },
    "workspace.image_gallery.quality": {
        "kind": "page",
        "title_key": "image_gallery.help.page.quality.title",
        "description_key": "image_gallery.help.page.quality.desc",
        "title": "Quality Metrics",
        "description": "Measured scores and the fidelity source",
        "icon": "analyze.svg",
        "body": "quality.md",
    },
    "workspace.image_gallery.ask_ai": {
        "kind": "page",
        "title_key": "image_gallery.help.page.ask_ai.title",
        "description_key": "image_gallery.help.page.ask_ai.desc",
        "title": "Ask AI",
        "description": "Questions about a selection or a series",
        "icon": "analyze.svg",
        "body": "ask_ai.md",
    },
}

_ALIASES = {
    "image_gallery": "workspace.image_gallery",
    "image_gallery_overview": "workspace.image_gallery.overview",
    "gallery_triage": "workspace.image_gallery.triage",
    "gallery_quality": "workspace.image_gallery.quality",
    "gallery_ask_ai": "workspace.image_gallery.ask_ai",
}


def resolve_help_icon(name: str) -> QIcon | None:
    for member in Icon:
        if member.value == name:
            icon = get_icon(member)
            if not icon.isNull():
                return icon
    return None


def build_help_contribution():  # type: ignore[no-untyped-def]
    """Return typed ``HelpContribution`` for ``image_gallery`` (isolated)."""
    from plugins.help.contribution import HelpContribution

    return HelpContribution(
        owner_tab="image_gallery",
        attach_under="workspace",
        child_ids=("workspace.image_gallery",),
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
