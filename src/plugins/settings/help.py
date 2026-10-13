"""Settings plugin help page contributed into the host Help tree."""

from __future__ import annotations

from pathlib import Path

_HELP_ROOT = Path(__file__).resolve().parent / "resources" / "help"

_NODES = {
    "platform.settings": {
        "kind": "page",
        "title_key": "help.page.settings.title",
        "description_key": "help.page.settings.desc",
        "title": "Settings",
        "description": "Appearance and performance",
        "icon": "settings.svg",
        "body": "settings.md",
    },
}

_ALIASES = {
    "settings": "platform.settings",
}


def build_help_plugin_contribution():  # type: ignore[no-untyped-def]
    """Return typed ``HelpPluginContribution`` for ``settings`` (isolated)."""
    from plugins.help.contribution import HelpPluginContribution

    # No ``resolve_icon``: the settings plugin ships no icon module (verified
    # 2026-10-12 — ``src/plugins/settings/`` has no ``icons.py``). The
    # ``settings.svg`` node icon still resolves in production through the
    # app icon pack probed first by ``plugins.help.icons.resolve_help_icon``.
    return HelpPluginContribution(
        owner_plugin="settings",
        attach_under="platform",
        child_ids=("platform.settings",),
        nodes=dict(_NODES),
        aliases=dict(_ALIASES),
        body_root=_HELP_ROOT,
        asset_root=_HELP_ROOT,
    )
