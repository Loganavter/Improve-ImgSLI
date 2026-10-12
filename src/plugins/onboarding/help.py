"""Onboarding plugin help page contributed into the host Help tree."""

from __future__ import annotations

from pathlib import Path

_HELP_ROOT = Path(__file__).resolve().parent / "resources" / "help"

_NODES = {
    "platform.getting_started": {
        "kind": "page",
        "title_key": "help.page.getting_started.title",
        "description_key": "help.page.getting_started.desc",
        "title": "Getting Started",
        "description": "Quick orientation",
        "icon": "play.svg",
        "body": "getting_started.md",
    },
}

_ALIASES = {
    "introduction": "platform.getting_started",
}


def build_help_plugin_contribution():  # type: ignore[no-untyped-def]
    """Return typed ``HelpPluginContribution`` for ``onboarding`` (isolated)."""
    from plugins.help.contribution import HelpPluginContribution

    # No ``resolve_icon``: the onboarding plugin ships no help icon resolver
    # (verified 2026-10-12 — ``src/plugins/onboarding/icons.py`` holds demo
    # slide icons only, no ``get_icon``/resolver). The ``play.svg`` node icon
    # still resolves in production through the app icon pack probed first by
    # ``plugins.help.icons.resolve_help_icon``.
    # The ``image_compare.action.save`` key ref in the moved body stays as-is  # ALLOWED: comment documents the shared key decision (no import, no coupling)
    # by explicit decision (recon Row 3 — the IC tab is always loaded, same
    # posture as the export Row 5 refs); no key fork.
    return HelpPluginContribution(
        owner_plugin="onboarding",
        attach_under="platform",
        child_ids=("platform.getting_started",),
        nodes=dict(_NODES),
        aliases=dict(_ALIASES),
        body_root=_HELP_ROOT,
        asset_root=_HELP_ROOT,
    )
