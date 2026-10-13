"""Plugin help contribution protocol: shape, merge guards, collection.

Phase 1 of the help per-owner refactor — protocol only, zero real plugin
contributions registered. Mirrors ``test_help_tree.py`` style; pure tree
ops, offscreen-safe (no widgets).
"""

from __future__ import annotations

import copy
import dataclasses

import pytest

from plugins.help.contribution import HelpContribution, HelpPluginContribution
from plugins.help.tree import (
    build_help_tree,
    clear_help_contributions,
    collect_help_plugin_contributions,
    contribute_all_help_plugins,
    install_help_plugin_contributions,
    load_help_tree,
    merge_help_contributions,
    merge_help_plugin_contributions,
)


def _fragment(
    *,
    owner_plugin: str = "export",
    node_id: str = "workspace.export",
    alias: str = "zz_plugin_demo",
    attach_under: str = "workspace",
) -> HelpPluginContribution:
    return HelpPluginContribution(
        owner_plugin=owner_plugin,
        attach_under=attach_under,
        child_ids=(node_id,),
        nodes={
            node_id: {
                "kind": "page",
                "title": "Export",
                "body": "export.md",
            }
        },
        aliases={alias: node_id},
    )


@pytest.fixture(autouse=True)
def _clean_tree():
    clear_help_contributions()
    yield
    clear_help_contributions()


def test_plugin_contribution_is_frozen():
    frag = _fragment()
    assert frag.__dataclass_params__.frozen is True
    with pytest.raises(dataclasses.FrozenInstanceError):
        frag.owner_plugin = "other"  # type: ignore[misc]


def test_plugin_contribution_shape_mirrors_tab_contribution():
    tab_fields = [f.name for f in dataclasses.fields(HelpContribution)]
    plugin_fields = [f.name for f in dataclasses.fields(HelpPluginContribution)]
    assert tab_fields == ["owner_tab"] + plugin_fields[1:]
    assert plugin_fields == [
        "owner_plugin",
        "attach_under",
        "child_ids",
        "nodes",
        "aliases",
        "body_root",
        "asset_root",
        "resolve_icon",
    ]


def test_plugin_contribution_owner_plugin_validation():
    with pytest.raises(ValueError):
        _fragment(owner_plugin="")
    with pytest.raises(ValueError):
        _fragment(owner_plugin="   ")
    assert _fragment(owner_plugin="export").owner_plugin == "export"


def test_plugin_contribution_duplicate_node_id_raises():
    base = load_help_tree()
    # Against a host node …
    with pytest.raises(KeyError):
        merge_help_plugin_contributions(base, [_fragment(node_id="about")])
    # … and against another plugin fragment in the same batch.
    with pytest.raises(KeyError):
        merge_help_plugin_contributions(
            base, [_fragment(), _fragment(alias="zz_plugin_demo_2")]
        )


def test_plugin_contribution_alias_conflict_raises():
    base = load_help_tree()
    conflicting = _fragment(alias="about")  # host "about" → "about", ours differs
    with pytest.raises(KeyError):
        merge_help_plugin_contributions(base, [conflicting])
    # Same slug → same target is idempotent, not a conflict.
    same_target = HelpPluginContribution(
        owner_plugin="help",
        attach_under="root",
        child_ids=(),
        nodes={},
        aliases={"about": "about"},
    )
    tree = merge_help_plugin_contributions(base, [same_target])
    assert tree.resolve_alias("about") == "about"


def test_plugin_contribution_merge_is_immutable():
    base = load_help_tree()
    frag = _fragment()
    nodes_snapshot = copy.deepcopy(frag.nodes)
    aliases_snapshot = dict(frag.aliases)
    child_ids_snapshot = tuple(frag.child_ids)
    host_children_before = tuple(base.require("workspace").children)
    tree = merge_help_plugin_contributions(base, [frag])
    assert frag.nodes == nodes_snapshot
    assert frag.aliases == aliases_snapshot
    assert frag.child_ids == child_ids_snapshot
    # Host base untouched; merged tree carries the new child.
    assert tuple(base.require("workspace").children) == host_children_before
    assert "workspace.export" in tree.require("workspace").children


def test_plugin_and_tab_namespaces_share_one_uniqueness_scope():
    base = load_help_tree()
    tab_frag = HelpContribution(
        owner_tab="image_compare",
        attach_under="workspace",
        child_ids=("workspace.shared",),
        nodes={"workspace.shared": {"kind": "hub", "title": "Shared"}},
        aliases={},
    )
    tab_merged = merge_help_contributions(base, [tab_frag])
    with pytest.raises(KeyError):
        merge_help_plugin_contributions(
            tab_merged, [_fragment(node_id="workspace.shared")]
        )


def test_zero_plugin_contributions_leave_tree_identical():
    before = build_help_tree()
    install_help_plugin_contributions([])
    after = build_help_tree()
    assert after == before
    assert set(after.nodes) == set(before.nodes)
    assert dict(after.aliases) == dict(before.aliases)


def test_collect_plugin_contributions_probes_duck_typed():
    class _Contributor:
        _plugin_meta = {"name": "export"}

        def build_help_plugin_contribution(self):
            return _fragment()

    class _ListContributor:
        _plugin_meta = {"name": "settings"}

        def build_help_plugin_contribution(self):
            return [_fragment(owner_plugin="settings", node_id="platform.zz", alias="zz_plugin_2", attach_under="platform")]

    class _Raiser:
        _plugin_meta = {"name": "broken"}

        def build_help_plugin_contribution(self):
            raise RuntimeError("boom")

    class _Silent:
        _plugin_meta = {"name": "layout"}

    class _WrongType:
        _plugin_meta = {"name": "weird"}

        def build_help_plugin_contribution(self):
            return "not-a-contribution"

    collected = collect_help_plugin_contributions(
        [_Contributor(), _ListContributor(), _Raiser(), _Silent(), _WrongType()]
    )
    assert [c.owner_plugin for c in collected] == ["export", "settings"]


def test_collect_plugin_contribution_owner_mismatch_still_collects():
    class _Mismatched:
        _plugin_meta = {"name": "export"}

        def build_help_plugin_contribution(self):
            return _fragment(owner_plugin="other")

    collected = collect_help_plugin_contributions([_Mismatched()])
    assert len(collected) == 1  # warns like the tab collector, still collects


def test_contribute_all_help_plugins_installs_into_tree():
    class _Contributor:
        _plugin_meta = {"name": "export"}

        def build_help_plugin_contribution(self):
            return _fragment()

    contribute_all_help_plugins([_Contributor()])
    tree = build_help_tree()
    assert "workspace.export" in tree.nodes
    assert tree.resolve_alias("zz_plugin_demo") == "workspace.export"
