"""Session Picker help icon resolver (web canon: structure is scanned).

Single-page package — the page title comes from its own ``##`` heading, so
this module only keeps the tab icon resolver for the hub-card/search chain.
"""

from __future__ import annotations

from PySide6.QtGui import QIcon

from tabs.session_picker.icons import Icon, get_icon


def resolve_help_icon(name: str) -> QIcon | None:
    for member in Icon:
        if member.value == name:
            icon = get_icon(member)
            if not icon.isNull():
                return icon
    return None


def build_help_hub_contribution():  # type: ignore[no-untyped-def]
    """Return the presentation fragment for ``session_picker`` (no hub)."""
    from plugins.help.contribution import HelpHubContribution

    return HelpHubContribution(
        owner_tab="session_picker",
        mount="workspace.session_picker",
        resolve_icon=resolve_help_icon,
    )
