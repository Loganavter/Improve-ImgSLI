"""Export plugin help hub contributed into the host Help tree."""

from __future__ import annotations

from pathlib import Path

_HELP_ROOT = Path(__file__).resolve().parent / "resources" / "help"

_NODES = {
    "workspace.export": {
        "kind": "page",
        "title_key": "image_compare.help.page.export.title",  # ALLOWED: shared i18n key namespace across the help owner boundary (title keys stay with the IC pack by explicit per-owner-refactor decision — no import, no coupling)
        "description_key": "image_compare.help.page.export.desc",  # ALLOWED: shared i18n key namespace across the help owner boundary (same decision as title_key)
        "title": "Export",
        "description": "Stills and quick-save",
        "icon": "save_icon.svg",
        "body": "export.md",
    },
}

_ALIASES = {
    "export": "workspace.export",
}


def build_help_plugin_contribution():  # type: ignore[no-untyped-def]
    """Return typed ``HelpPluginContribution`` for ``export`` (isolated)."""
    from plugins.help.contribution import HelpPluginContribution

    # No ``resolve_icon``: the export plugin ships no icon module (verified
    # 2026-10-12 — ``src/plugins/export/`` has no ``icons.py``). The
    # ``save_icon.svg`` node icon still resolves in production through the
    # image_compare tab's ``resolve_help_icon`` in the merged resolver chain.  # ALLOWED: comment documents the shared icon resolver chain (no import, no coupling)
    return HelpPluginContribution(
        owner_plugin="export",
        attach_under="workspace",
        child_ids=("workspace.export",),
        nodes=dict(_NODES),
        aliases=dict(_ALIASES),
        body_root=_HELP_ROOT,
        asset_root=_HELP_ROOT,
    )
