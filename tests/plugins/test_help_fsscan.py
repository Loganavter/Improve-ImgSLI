"""Phase 1 web-canon: the fs-scanned tree matches the registry tree (structure).

Pins ids, kinds, body paths and children-sets of ``scan_help_tree()`` against
the merged ``tree.json`` + contributions tree. Titles/descriptions/icons are
NOT compared here (phase 2 derives them from ``##`` headings).
"""

from __future__ import annotations


def _ensure_merged_tree():
    from plugins.help.tree import (
        clear_help_contributions,
        collect_help_plugin_contributions,
        get_help_tree,
        install_help_plugin_contributions,
    )
    from tabs.registry import TabRegistry

    clear_help_contributions()
    tabs = TabRegistry()
    tabs.discover()
    tabs.contribute_all_help()
    from plugins.export.plugin import ExportPlugin
    from plugins.image_properties.plugin import ImagePropertiesPlugin
    from plugins.onboarding.plugin import OnboardingPlugin
    from plugins.settings.plugin import SettingsPlugin

    install_help_plugin_contributions(
        collect_help_plugin_contributions(
            [ExportPlugin(), SettingsPlugin(), ImagePropertiesPlugin(), OnboardingPlugin()]
        )
    )
    return get_help_tree()


def test_fsscan_matches_registry_structure():
    from plugins.help.scan import scan_help_tree

    registry = _ensure_merged_tree()
    scanned = scan_help_tree()

    assert set(scanned.nodes) == set(registry.nodes)
    assert scanned.root_id == registry.root_id
    for node_id, expected in registry.nodes.items():
        actual = scanned.nodes[node_id]
        assert actual.kind == expected.kind, node_id
        assert actual.body == expected.body, node_id
        left = actual.body_root.resolve() if actual.body_root is not None else None
        right = expected.body_root.resolve() if expected.body_root is not None else None
        assert left == right, node_id
        assert set(actual.children) == set(expected.children), node_id
