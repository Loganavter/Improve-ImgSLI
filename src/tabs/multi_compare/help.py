"""Multi Compare help hub presentation (web canon: structure is scanned)."""

from __future__ import annotations

from PySide6.QtGui import QIcon

from tabs.multi_compare.icons import Icon, get_icon


def resolve_help_icon(name: str) -> QIcon | None:
    for member in Icon:
        if member.value == name:
            icon = get_icon(member)
            if not icon.isNull():
                return icon
    return None


def build_help_hub_contribution():  # type: ignore[no-untyped-def]
    """Return the hub presentation fragment for ``multi_compare``."""
    from plugins.help.contribution import HelpHubContribution

    return HelpHubContribution(
        owner_tab="multi_compare",
        mount="workspace.multi_compare",
        title="Multi Compare",
        description="Many-image layouts",
        icon="grid.svg",
        title_key="workspace.session_types.multi_compare",
        description_key="multi_compare.help.hub.desc",
        resolve_icon=resolve_help_icon,
    )
