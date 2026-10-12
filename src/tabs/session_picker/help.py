"""Session Picker help subtree contributed into the host Help tree."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QIcon

from tabs.session_picker.icons import Icon, get_icon

_HELP_ROOT = Path(__file__).resolve().parent / "resources" / "help"

# Phase 4: the host ``platform.workspace`` page moves here byte-identical as
# ``workspace.session_picker`` (a page, not a hub — the slug-freeze asserts
# pin the ``session_picker``/``workspace_tabs`` aliases to a page node, and
# topic search content-matches the moved body). The pre-existing hub wrapper
# of the same id (overview only) is flattened so the tasked id stays verbatim;
# the overview page reparents directly under ``workspace`` unchanged.
_NODES = {
    "workspace.session_picker": {
        "kind": "page",
        "title_key": "help.page.workspace.title",
        "description_key": "help.page.workspace.desc",
        "title": "Workspace Tabs",
        "description": "Session picker and tab strip",
        "icon": "add.svg",
        "body": "workspace.md",
    },
    "workspace.session_picker.overview": {
        "kind": "page",
        "title_key": "session_picker.help.page.overview.title",
        "description_key": "session_picker.help.page.overview.desc",
        "title": "Session Picker Overview",
        "description": "Create sessions and reopen recent projects",
        "icon": "add.svg",
        "body": "overview.md",
    },
}

_ALIASES = {
    "session_picker": "workspace.session_picker",
    "workspace_tabs": "workspace.session_picker",
    "session_picker_overview": "workspace.session_picker.overview",
    "sp_overview": "workspace.session_picker.overview",
}


def resolve_help_icon(name: str) -> QIcon | None:
    for member in Icon:
        if member.value == name:
            icon = get_icon(member)
            if not icon.isNull():
                return icon
    return None


def build_help_contribution():  # type: ignore[no-untyped-def]
    """Return typed ``HelpContribution`` for ``session_picker`` (isolated)."""
    from plugins.help.contribution import HelpContribution

    return HelpContribution(
        owner_tab="session_picker",
        attach_under="workspace",
        child_ids=(
            "workspace.session_picker",
            "workspace.session_picker.overview",
        ),
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
