"""Help tree paths, hub fragments, and navigation stack."""

from __future__ import annotations

import pytest

from plugins.help.navigator import HelpNavigator
from plugins.help.tree import (
    clear_help_contributions,
    get_help_tree,
    host_help_root,
    install_help_contributions,
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


def test_help_tree_loads_and_paths_resolve():
    _ensure_help_contributions()
    tree = get_help_tree()
    assert tree.root_id == "root"
    assert tree.resolve_path("workspace.image_compare.magnifier") == (
        "workspace.image_compare.magnifier"
    )
    assert tree.resolve_path("about") == "about"
    assert tree.resolve_path("platform.hotkeys") == "platform.hotkeys"
    assert tree.resolve_path("workspace.image_compare.video") == (
        "workspace.image_compare.video"
    )
    assert tree.resolve_path("workspace.multi_compare.overview") == (
        "workspace.multi_compare.overview"
    )
    assert tree.resolve_path("platform.image_properties") == "platform.image_properties"
    assert tree.resolve_path("workspace.session_picker") == "workspace.session_picker"
    # Bare "workspace" is the Workspace hub, not the platform page.
    assert tree.resolve_path("workspace") == "workspace"
    assert tree.require("root").children[0] == "about"
    about = tree.require("about")
    assert about.kind == "page"
    assert about.body == "about.md"
    from plugins.help.labels import node_title

    assert node_title(about, "en") == "About"
    assert tree.require("workspace").icon == "photo_icon.svg"
    assert tree.require("workspace").title_key == "help.hub.workspace.title"
    assert "workspace.image_compare" in tree.require("workspace").children
    assert "workspace.multi_compare" in tree.require("workspace").children
    assert "workspace.image_compare.video" in tree.require("workspace.image_compare").children
    assert "workspace.image_compare.export" not in tree.nodes
    assert (
        "workspace.image_compare.export"
        not in tree.require("workspace.image_compare").children
    )
    assert "workspace.export" in tree.require("workspace").children
    assert tree.resolve_path("workspace.export") == "workspace.export"
    export = tree.require("workspace.export")
    assert export.kind == "page"
    assert export.body == "export.md"
    assert export.body_root is not None
    assert (export.body_root / "en" / export.body).is_file()
    platform_children = tree.require("platform").children
    assert "platform.getting_started" in platform_children
    assert "platform.image_properties" in platform_children
    assert "platform.tabs" in platform_children
    node = tree.require("workspace.image_compare.magnifier")
    assert node.kind == "page"
    assert node.body == "magnifier.md"
    assert node.body_root is not None
    assert (node.body_root / "en" / node.body).is_file()
    video = tree.require("workspace.image_compare.video")
    assert video.body == "video.md"
    assert (video.body_root / "en" / video.body).is_file()
    assert (video.body_root / "ru" / video.body).is_file()
    props = tree.require("platform.image_properties")
    assert props.body == "image_properties.md"
    assert props.body_root is not None
    for lang in ("en", "ru", "zh", "pt_BR"):
        assert (props.body_root / lang / props.body).is_file()
    ws = tree.require("workspace.session_picker")
    assert ws.body == "sessions.md"
    assert ws.body_root is not None
    for lang in ("en", "ru", "zh", "pt_BR"):
        assert (ws.body_root / lang / ws.body).is_file()
    root = host_help_root()
    for lang in ("en", "ru", "zh", "pt_BR"):
        assert (root / lang / about.body).is_file()


def test_help_hub_fragment_overlays_hub_presentation():
    from plugins.help.contribution import HelpHubContribution
    from plugins.help.scan import scan_help_tree

    clear_help_contributions()
    frag = HelpHubContribution(
        owner_tab="image_compare",
        mount="workspace.image_compare",
        title="Compare!",
        description="Demo hub",
        icon="demo.svg",
    )
    tree = scan_help_tree([frag])
    hub = tree.require("workspace.image_compare")
    assert hub.title == "Compare!"
    assert hub.description == "Demo hub"
    assert hub.icon == "demo.svg"
    # Pages are untouched by the fragment.
    assert tree.require("workspace.image_compare.comparison").body == "comparison.md"


def test_install_help_contributions_updates_cached_tree():
    from plugins.help.contribution import HelpHubContribution

    clear_help_contributions()
    before = get_help_tree()
    assert before.require("workspace.image_compare").title == "workspace.image_compare"
    frag = HelpHubContribution(
        owner_tab="image_compare",
        mount="workspace.image_compare",
        title="Compare!",
    )
    tree = install_help_contributions([frag])
    assert tree.require("workspace.image_compare").title == "Compare!"
    assert get_help_tree() is tree


def test_help_tree_path_to_magnifier():
    _ensure_help_contributions()
    tree = get_help_tree()
    path = tree.path_to("workspace.image_compare.magnifier")
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


def test_help_entry_point_paths_resolve():
    """Entry points (F1 / Learn-more / ``help_page``) resolve to readable pages.

    Replaces the alias freeze: actions carry dotted paths, so this pins the
    path set they use instead of a slug map.
    """
    from plugins.help.tree import read_help_page_markdown

    _ensure_help_contributions()
    tree = get_help_tree()
    expected = [
        "about",
        "platform.getting_started",
        "platform.file_project",
        "platform.settings",
        "platform.hotkeys",
        "platform.tabs",
        "platform.image_properties",
        "workspace.session_picker",
        "workspace.export",
        "workspace.image_compare.comparison",
        "workspace.image_compare.magnifier",
        "workspace.image_compare.video",
        "workspace.multi_compare.overview",
        "workspace.multi_compare.layouts",
        "workspace.multi_compare.viewing",
        "workspace.multi_compare.export",
        "workspace.image_gallery.overview",
        "workspace.image_gallery.triage",
        "workspace.image_gallery.quality",
        "workspace.image_gallery.ask_ai",
    ]
    for node_id in expected:
        assert tree.resolve_path(node_id) == node_id, node_id
        node = tree.require(node_id)
        assert node.kind == "page", node_id
        assert node.body, node_id
        md = read_help_page_markdown("en", node.body, body_root=node.body_root)
        assert md.strip(), node_id
        assert not md.startswith("## Missing page"), node_id


def test_help_alias_slug_freeze_tab_contributions():
    """Tab hub pages resolve to their contributed nodes (paths, not slugs)."""
    from plugins.help.tree import read_help_page_markdown

    _ensure_help_contributions()
    tree = get_help_tree()
    expected = [
        "workspace.image_compare.comparison",
        "workspace.image_compare.magnifier",
        "workspace.export",
        "workspace.image_compare.video",
        "workspace.multi_compare.overview",
        "workspace.multi_compare.layouts",
        "workspace.multi_compare.viewing",
        "workspace.multi_compare.export",
        "workspace.session_picker",
        "workspace.image_gallery.overview",
        "workspace.image_gallery.triage",
        "workspace.image_gallery.quality",
        "workspace.image_gallery.ask_ai",
    ]
    for node_id in expected:
        assert tree.resolve_path(node_id) == node_id, node_id
        node = tree.require(node_id)
        assert node.kind == "page", node_id
        assert node.body, node_id
        md = read_help_page_markdown("en", node.body, body_root=node.body_root)
        assert md.strip(), node_id
        assert not md.startswith("## Missing page"), node_id


def test_help_alias_gallery_hub_resolves():
    """The gallery hub path resolves to the hub node with its pages."""
    _ensure_help_contributions()
    tree = get_help_tree()
    assert tree.resolve_path("workspace.image_gallery") == "workspace.image_gallery"
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
    """Negative control: unknown paths raise (proves the pin tests bite)."""
    _ensure_help_contributions()
    tree = get_help_tree()
    with pytest.raises(KeyError):
        tree.resolve_path("no_such_help_topic_xyz")