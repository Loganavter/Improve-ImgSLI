"""Image-properties plugin help page contributed into the host Help tree."""

from __future__ import annotations

from pathlib import Path

_HELP_ROOT = Path(__file__).resolve().parent / "resources" / "help"

_NODES = {
    "platform.image_properties": {
        "kind": "page",
        "title_key": "help.page.image_properties.title",
        "description_key": "help.page.image_properties.desc",
        "title": "Image Properties",
        "description": "File metadata and in-app context",
        "icon": "link.svg",
        "body": "image_properties.md",
    },
}

_ALIASES = {
    "image_properties": "platform.image_properties",
}


def build_help_plugin_contribution():  # type: ignore[no-untyped-def]
    """Return typed ``HelpPluginContribution`` for ``image_properties`` (isolated)."""
    from plugins.help.contribution import HelpPluginContribution

    # No ``resolve_icon``: the image_properties plugin ships no icon module
    # (verified 2026-10-12 — ``src/plugins/image_properties/`` has no
    # ``icons.py``). The ``link.svg`` node icon still resolves in production
    # through the app icon pack probed first by
    # ``plugins.help.icons.resolve_help_icon``.
    return HelpPluginContribution(
        owner_plugin="image_properties",
        attach_under="platform",
        child_ids=("platform.image_properties",),
        nodes=dict(_NODES),
        aliases=dict(_ALIASES),
        body_root=_HELP_ROOT,
        asset_root=_HELP_ROOT,
    )
