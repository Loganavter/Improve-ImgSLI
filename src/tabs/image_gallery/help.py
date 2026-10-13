"""Image Gallery help hub presentation (web canon: structure is scanned)."""

from __future__ import annotations

from PySide6.QtGui import QIcon

from tabs.image_gallery.icons import Icon, get_icon


def resolve_help_icon(name: str) -> QIcon | None:
    for member in Icon:
        if member.value == name:
            icon = get_icon(member)
            if not icon.isNull():
                return icon
    return None


def build_help_hub_contribution():  # type: ignore[no-untyped-def]
    """Return the hub presentation fragment for ``image_gallery``."""
    from plugins.help.contribution import HelpHubContribution

    return HelpHubContribution(
        owner_tab="image_gallery",
        mount="workspace.image_gallery",
        title="Image Gallery",
        description="Browse, triage, and review image folders",
        icon="gallery.svg",
        title_key="image_gallery.help.hub.title",
        description_key="image_gallery.help.hub.desc",
        resolve_icon=resolve_help_icon,
    )
