"""Help tree aliases, contribution merge, and navigation stack."""

from __future__ import annotations

import pytest

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
    from pathlib import Path

    from resources.translations import add_i18n_root
    from tabs.registry import TabRegistry

    clear_help_contributions()
    # Phase 3a: settings.* keys live in the settings plugin pack (moved
    # from the host pack). Production registers plugin packs at discovery
    # (registry auto-registers <pkg>/resources/i18n); test sessions that
    # skip plugin discovery register the owner pack explicitly — same
    # posture as the export-pack add_i18n_root in export dialog tests.
    add_i18n_root(Path("src/plugins/settings/resources/i18n"))
    tabs = TabRegistry()
    tabs.discover()
    tabs.contribute_all_help()
    # Phase 2: the export hub is plugin-owned — install it the way HelpPlugin
    # does in production (duck-typed probe of the plugin instance).
    from plugins.export.plugin import ExportPlugin
    from plugins.help.tree import (
        collect_help_plugin_contributions,
        install_help_plugin_contributions,
    )

    # Phase 2+3+4: the export hub and the settings / image_properties /
    # getting_started pages are plugin-owned — install them the way HelpPlugin
    # does in production (duck-typed probe of the plugin instances). NOTE:
    # install REPLACES the plugin list, so all plugin instances are collected
    # in one call.
    from plugins.image_properties.plugin import ImagePropertiesPlugin
    from plugins.settings.plugin import SettingsPlugin
    from plugins.onboarding.plugin import OnboardingPlugin

    install_help_plugin_contributions(
        collect_help_plugin_contributions(
            [ExportPlugin(), SettingsPlugin(), ImagePropertiesPlugin(), OnboardingPlugin()]
        )
    )


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
    assert tree.resolve_alias("session_picker") == "workspace.session_picker"
    assert tree.resolve_alias("workspace_tabs") == "workspace.session_picker"
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
    # Phase 2: export hub moved IC tab → export plugin (node id changes,
    # alias "export" preserved and retargeted to workspace.export).
    assert "workspace.image_compare.export" not in tree.nodes
    assert (
        "workspace.image_compare.export"
        not in tree.require("workspace.image_compare").children
    )
    assert "workspace.export" in tree.require("workspace").children
    assert tree.resolve_alias("export") == "workspace.export"
    export = tree.require(tree.resolve_alias("export"))
    assert export.kind == "page"
    assert export.body == "export.md"
    assert export.body_root is not None
    assert (export.body_root / "en" / export.body).is_file()
    platform_children = tree.require("platform").children
    assert "platform.getting_started" in platform_children
    assert "platform.image_properties" in platform_children
    assert "platform.tabs" in platform_children
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
    assert props.body == "image_properties.md"
    assert props.body_root is not None
    for lang in ("en", "ru", "zh", "pt_BR"):
        assert (props.body_root / lang / props.body).is_file()
    ws = tree.require(tree.resolve_alias("session_picker"))
    assert ws.body == "sessions.md"
    assert ws.body_root is not None
    for lang in ("en", "ru", "zh", "pt_BR"):
        assert (ws.body_root / lang / ws.body).is_file()
    root = host_help_root()
    for lang in ("en", "ru", "zh", "pt_BR"):
        assert (root / lang / about.body).is_file()


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


def test_help_alias_slug_freeze_host():
    """Slug freeze: host aliases keep resolving so content moves can't break links.

    Pins the ``tree.json`` ``aliases`` map (F1 / Learn-more / ``help://``).
    Each alias must resolve to its node AND the target page body must be
    readable — mapping alone is not enough.
    """
    from plugins.help.tree import read_help_page_markdown

    _ensure_help_contributions()
    tree = get_help_tree()
    expected = {
        "about": "about",
        "introduction": "platform.getting_started",
        "file_management": "platform.file_project",
        "settings": "platform.settings",
        "hotkeys": "platform.hotkeys",
        "tabs": "platform.tabs",
        "image_properties": "platform.image_properties",
        "session_picker": "workspace.session_picker",
        "workspace_tabs": "workspace.session_picker",
    }
    for alias, node_id in expected.items():
        assert tree.resolve_alias(alias) == node_id, alias
        node = tree.require(node_id)
        assert node.kind == "page", alias
        assert node.body, alias
        md = read_help_page_markdown("en", node.body, body_root=node.body_root)
        assert md.strip(), alias
        assert not md.startswith("## Missing page"), alias


def test_help_alias_slug_freeze_tab_contributions():
    """Slug freeze: tab ``_ALIASES`` keep resolving to their contributed nodes."""
    from plugins.help.tree import read_help_page_markdown

    _ensure_help_contributions()
    tree = get_help_tree()
    expected = {
        # tabs/image_compare/help.py _ALIASES
        "comparison": "workspace.image_compare.comparison",
        "magnifier": "workspace.image_compare.magnifier",
        # Phase 2: export hub moved to the export plugin (alias preserved,
        # retargeted) — src/plugins/export/help.py _ALIASES
        "export": "workspace.export",
        "video": "workspace.image_compare.video",
        # tabs/multi_compare/help.py _ALIASES
        "multi_compare": "workspace.multi_compare.overview",
        "multi_compare_overview": "workspace.multi_compare.overview",
        "mc_overview": "workspace.multi_compare.overview",
        "mc_layouts": "workspace.multi_compare.layouts",
        "mc_viewing": "workspace.multi_compare.viewing",
        "mc_export": "workspace.multi_compare.export",
        # tabs/session_picker/help.py _ALIASES
        "session_picker_overview": "workspace.session_picker",
        "sp_overview": "workspace.session_picker",
        # tabs/image_gallery/help.py _ALIASES (page targets)
        "image_gallery_overview": "workspace.image_gallery.overview",
        "gallery_triage": "workspace.image_gallery.triage",
        "gallery_quality": "workspace.image_gallery.quality",
        "gallery_ask_ai": "workspace.image_gallery.ask_ai",
    }
    for alias, node_id in expected.items():
        assert tree.resolve_alias(alias) == node_id, alias
        node = tree.require(node_id)
        assert node.kind == "page", alias
        assert node.body, alias
        md = read_help_page_markdown("en", node.body, body_root=node.body_root)
        assert md.strip(), alias
        assert not md.startswith("## Missing page"), alias


def test_help_alias_gallery_hub_resolves():
    """Slug freeze: the ``image_gallery`` hub alias resolves to the hub node."""
    _ensure_help_contributions()
    tree = get_help_tree()
    assert tree.resolve_alias("image_gallery") == "workspace.image_gallery"
    hub = tree.require("workspace.image_gallery")
    assert hub.kind == "hub"
    assert "workspace.image_gallery" in tree.require("workspace").children
    for child_id in (
        "workspace.image_gallery.overview",
        "workspace.image_gallery.triage",
        "workspace.image_gallery.quality",
        "workspace.image_gallery.ask_ai",
    ):
        assert child_id in hub.children, child_id


def test_help_alias_unknown_slug_raises():
    """Negative control: unknown slugs raise (proves the freeze tests bite)."""
    _ensure_help_contributions()
    tree = get_help_tree()
    with pytest.raises(KeyError):
        tree.resolve_alias("no_such_help_topic_xyz")