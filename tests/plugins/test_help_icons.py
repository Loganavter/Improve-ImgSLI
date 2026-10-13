"""Help card icons: every hub and page must carry a resolvable icon.

Hubs get theirs from ``HOST_HUB_META`` / tab ``HelpHubContribution`` fragments
(frozen today). Pages get theirs from the leading ``icon:`` frontmatter — the
authoring wave fills those separately, so the page gate escalates from a
documented ``xfail`` to a hard failure the moment the first page icon lands
(see ``DONE.md``).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from plugins.help.tree import HelpTree, clear_help_contributions, get_help_tree


def _build_tree() -> HelpTree:
    from resources.translations import add_i18n_root
    from tabs.registry import TabRegistry

    clear_help_contributions()
    add_i18n_root(Path("src/plugins/settings/resources/i18n"))
    tabs = TabRegistry()
    tabs.discover()
    tabs.contribute_all_help()
    return get_help_tree()


def _icon_resolvable(name: str | None, resolvers: tuple) -> bool:
    """True when ``name`` resolves to a real icon (not the HELP fallback)."""
    if not name:
        return False
    from ui.icon_manager import get_app_icon

    if not get_app_icon(name).isNull():
        return True
    for resolver in resolvers:
        try:
            found = resolver(name)
        except Exception:
            continue
        if found is not None and not found.isNull():
            return True
    return False


def test_every_help_hub_has_a_resolvable_icon():
    tree = _build_tree()
    missing = sorted(
        node.node_id
        for node in tree.nodes.values()
        if node.kind == "hub" and not _icon_resolvable(node.icon, tree.icon_resolvers)
    )
    assert not missing, (
        "help hubs without a resolvable icon (fix HOST_HUB_META in scan.py or the "
        "tab HelpHubContribution fragment): " + ", ".join(missing)
    )


def test_every_help_page_has_a_resolvable_icon():
    tree = _build_tree()
    missing = sorted(
        node.node_id
        for node in tree.nodes.values()
        if node.kind == "page" and not _icon_resolvable(node.icon, tree.icon_resolvers)
    )
    if not missing:
        return
    pages_with_icon = [n for n in tree.nodes.values() if n.kind == "page" and n.icon]
    detail = ", ".join(missing)
    if not pages_with_icon:
        pytest.xfail(
            "authoring wave not landed: no page body carries an `icon:` frontmatter "
            "key yet, so every page lacks an icon. Once it lands, add `icon: <name>` "
            "to the frontmatter of: " + detail
        )
    pytest.fail(
        "help pages without a resolvable icon — add `icon: <name>` frontmatter to "
        "the page body (name must resolve via get_app_icon or the tab resolver): "
        + detail
    )
