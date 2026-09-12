"""Help tree aliases, contribution merge, and navigation stack."""

from __future__ import annotations

from plugins.help.contribution import HelpContributionRegistry
from plugins.help.navigator import HelpNavigator
from plugins.help.tree import (
    clear_help_contributions,
    get_help_tree,
    host_help_root,
    install_help_contributions,
    load_help_tree,
    merge_help_contributions,
)


def _ensure_help_contributions() -> None:
    from tabs.registry import TabRegistry

    clear_help_contributions()
    tabs = TabRegistry()
    tabs.discover()
    tabs.contribute_all_help()


def test_help_tree_loads_and_aliases_resolve():
    _ensure_help_contributions()
    tree = get_help_tree()
    assert tree.root_id == "root"
    assert tree.resolve_alias("magnifier") == "workspace.image_compare.magnifier"
    assert tree.resolve_alias("about") == "about"
    assert tree.resolve_alias("hotkeys") == "platform.hotkeys"
    assert tree.resolve_alias("video") == "workspace.image_compare.video"
    assert tree.resolve_alias("multi_compare") == "workspace.multi_compare.overview"
    assert tree.resolve_alias("image_properties") == "platform.image_properties"
    assert tree.resolve_alias("session_picker") == "platform.workspace"
    assert tree.resolve_alias("workspace_tabs") == "platform.workspace"
    # Bare "workspace" is the Workspace hub, not the platform page.
    assert tree.resolve_alias("workspace") == "workspace"
    assert tree.require("root").children[0] == "about"
    about = tree.require("about")
    assert about.kind == "page"
    assert about.body == "about.md"
    assert about.title_key == "help.page.about.title"
    assert tree.require("workspace").icon == "photo_icon.svg"
    assert tree.require("workspace").title_key == "help.hub.workspace.title"
    assert "workspace.image_compare" in tree.require("workspace").children
    assert "workspace.multi_compare" in tree.require("workspace").children
    assert "workspace.image_compare.video" in tree.require("workspace.image_compare").children
    platform_children = tree.require("platform").children
    assert "platform.workspace" in platform_children
    assert "platform.image_properties" in platform_children
    node = tree.require(tree.resolve_alias("magnifier"))
    assert node.kind == "page"
    assert node.body == "magnifier.md"
    assert node.body_root is not None
    assert (node.body_root / "en" / node.body).is_file()
    video = tree.require(tree.resolve_alias("video"))
    assert video.body == "video.md"
    assert (video.body_root / "en" / video.body).is_file()
    assert (video.body_root / "ru" / video.body).is_file()
    props = tree.require(tree.resolve_alias("image_properties"))
    assert props.body == "platform/image_properties.md"
    ws = tree.require(tree.resolve_alias("session_picker"))
    assert ws.body == "platform/workspace.md"
    root = host_help_root()
    for lang in ("en", "ru", "zh", "pt_BR"):
        assert (root / lang / about.body).is_file()
    for lang in ("en", "ru"):
        assert (root / lang / props.body).is_file()
        assert (root / lang / ws.body).is_file()


def test_host_tree_excludes_tab_topics_until_merge():
    clear_help_contributions()
    host = load_help_tree()
    assert host.require("workspace").children == ()
    assert "workspace.image_compare" not in host.nodes
    assert "magnifier" not in host.aliases


def test_help_contribution_merge_attaches_under_workspace(tmp_path):
    clear_help_contributions()
    host = load_help_tree()
    registry = HelpContributionRegistry()
    body = tmp_path / "help"
    (body / "en").mkdir(parents=True)
    (body / "en" / "demo.md").write_text(
        "# Demo\n\n:::figure{side=right}\n![x](assets/ui/placeholder.png)\nCap\n:::\n\n### Step\nText.\n",
        encoding="utf-8",
    )
    registry.contribute(
        attach_under="workspace",
        child_ids=("workspace.demo",),
        nodes={
            "workspace.demo": {
                "kind": "hub",
                "title": "Demo",
                "children": ["workspace.demo.page"],
            },
            "workspace.demo.page": {
                "kind": "page",
                "title": "Demo page",
                "body": "demo.md",
            },
        },
        aliases={"demo": "workspace.demo.page"},
        body_root=body,
    )
    tree = merge_help_contributions(host, registry)
    assert "workspace.demo" in tree.require("workspace").children
    assert tree.resolve_alias("demo") == "workspace.demo.page"
    assert tree.require("workspace.demo.page").body_root == body


def test_install_help_contributions_updates_cached_tree(tmp_path):
    clear_help_contributions()
    assert "workspace.image_compare" not in get_help_tree().nodes
    registry = HelpContributionRegistry()
    body = tmp_path / "help"
    (body / "en").mkdir(parents=True)
    (body / "en" / "x.md").write_text(
        "Intro\n\n:::figure{side=left}\n![a](a.png)\nc\n:::\n\n### A\nB\n",
        encoding="utf-8",
    )
    registry.contribute(
        attach_under="workspace",
        child_ids=("workspace.x",),
        nodes={
            "workspace.x": {
                "kind": "page",
                "title": "X",
                "body": "x.md",
            }
        },
        body_root=body,
    )
    tree = install_help_contributions(registry)
    assert "workspace.x" in tree.nodes
    assert "workspace.x" in get_help_tree().nodes


def test_help_tree_path_to_magnifier():
    _ensure_help_contributions()
    tree = get_help_tree()
    path = tree.path_to("magnifier")
    assert path[0] == "root"
    assert path[-1] == "workspace.image_compare.magnifier"
    assert "workspace" in path
    assert "workspace.image_compare" in path


def test_navigator_drill_and_back():
    _ensure_help_contributions()
    tree = get_help_tree()
    nav = HelpNavigator(tree)
    assert nav.current_id == "root"
    nav.push("workspace")
    nav.push("workspace.image_compare")
    nav.push("workspace.image_compare.magnifier")
    assert nav.current_id == "workspace.image_compare.magnifier"
    assert nav.can_go_back()
    nav.pop()
    assert nav.current_id == "workspace.image_compare"
    assert nav.can_go_forward()
    nav.go_forward()
    assert nav.current_id == "workspace.image_compare.magnifier"
    assert not nav.can_go_forward()
    nav.pop_to("root")
    assert nav.current_id == "root"


def test_navigator_mouse_forward_cleared_on_new_push():
    _ensure_help_contributions()
    tree = get_help_tree()
    nav = HelpNavigator(tree)
    nav.push("workspace.image_compare.magnifier")
    nav.pop()
    assert nav.can_go_forward()
    nav.push("workspace.image_compare.comparison")
    assert not nav.can_go_forward()
    assert nav.current_id == "workspace.image_compare.comparison"


def test_navigator_replace_sibling():
    _ensure_help_contributions()
    tree = get_help_tree()
    nav = HelpNavigator(tree)
    nav.push("workspace.image_compare.magnifier")
    nav.replace_sibling("workspace.image_compare.comparison")
    assert nav.current_id == "workspace.image_compare.comparison"
    assert nav.stack[-2] == "workspace.image_compare"


def test_load_help_tree_validates(tmp_path):
    bad = tmp_path / "tree.json"
    bad.write_text(
        '{"version":1,"root_id":"root","aliases":{},"nodes":{"root":{"kind":"hub","title":"R","children":["missing"]}}}',
        encoding="utf-8",
    )
    try:
        load_help_tree(bad)
        assert False, "expected KeyError"
    except KeyError:
        pass


def test_help_page_bodies_are_scenario_cards():
    """Leaf pages are scenario topics with stable h3 sections — figures optional."""
    from plugins.help.tree import read_help_page_markdown

    _ensure_help_contributions()
    tree = get_help_tree()
    pages = [n for n in tree.nodes.values() if n.kind == "page" and n.body]
    assert pages
    for lang in ("en", "ru"):
        for node in pages:
            md = read_help_page_markdown(
                lang, node.body, body_root=node.body_root
            )
            assert md.strip(), (lang, node.node_id)
            assert "TODO rewrite" not in md, (lang, node.node_id)
            assert md.lstrip().startswith("## "), (lang, node.node_id, "need page title")
            assert "### " in md, (lang, node.node_id, "need scenario sections")
            assert "### Related" not in md and "### Связанное" not in md, (
                lang,
                node.node_id,
            )
            # HelpDocumentView has no GFM table support — pipe rows collapse
            # into one paragraph (see HELP_SYSTEM.md Rendering).
            for line in md.splitlines():
                stripped = line.strip()
                if stripped.startswith("|") and stripped.endswith("|"):
                    assert False, (
                        lang,
                        node.node_id,
                        "GFM pipe table not supported; use bullet lists",
                        stripped[:80],
                    )
