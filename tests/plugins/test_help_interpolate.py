"""Help markdown ``{{tr:…}}`` / ``{{img:…}}`` interpolation."""

from __future__ import annotations

from pathlib import Path

from plugins.help.interpolate import (
    clear_help_figures_cache,
    interpolate_help_markdown,
    load_help_figures,
    resolve_help_figure,
)
from plugins.help.tree import get_help_tree, read_help_page_markdown, resolve_help_asset
from resources.translations import add_i18n_root


def _ensure_image_compare_i18n() -> None:
    add_i18n_root(Path("src/tabs/image_compare/resources/i18n"))


def test_interpolate_help_markdown_resolves_tab_action_keys():
    _ensure_image_compare_i18n()
    text = "Click **{{tr:image_compare.action.magnifier}}** or `M`."
    ru = interpolate_help_markdown(text, "ru")
    en = interpolate_help_markdown(text, "en")
    assert "Переключить лупу" in ru
    assert "{{tr:" not in ru
    assert "Toggle Magnifier" in en


def test_interpolate_help_markdown_resolves_img_slots():
    clear_help_figures_cache()
    text = "![x]({{img:platform.workspace.session_picker}})"
    out = interpolate_help_markdown(text, "en")
    assert out == "![x](platform/session_picker.jpg)"
    assert "{{img:" not in out


def test_interpolate_help_markdown_keeps_unknown_img_slot():
    clear_help_figures_cache()
    text = "![x]({{img:does.not.exist}})"
    assert interpolate_help_markdown(text, "en") == text


def test_help_figures_map_covers_budgeted_slots_and_assets_exist():
    clear_help_figures_cache()
    from tabs.registry import TabRegistry

    TabRegistry().discover()
    TabRegistry().contribute_all_help()
    tree = get_help_tree()
    figures = load_help_figures()
    required = {
        "ui.buttons.toolbar",
        "ui.buttons.mode_beginner",
        "ui.buttons.mode_advanced",
        "ui.buttons.mode_expert",
        "ui.buttons.long_press",
        "ui.lists_flyouts.list_manager",
        "ui.lists_flyouts.toolbar_flyouts",
        "ui.canvas_navigation.zoom",
        "platform.workspace.session_picker",
        "platform.image_properties.open",
        "platform.file_project.paste_overlay",
        "workspace.image_compare.comparison.split_line",
        "workspace.image_compare.comparison.difference_modes",
        "workspace.image_compare.magnifier.enabling",
        "workspace.image_compare.magnifier.combined_mode",
        "workspace.image_compare.export.dialog",
        "workspace.image_compare.video.timeline",
        "workspace.image_compare.video.export_encode",
        "workspace.multi_compare.overview.layouts",
    }
    assert required <= set(figures)
    for slot in required:
        path = resolve_help_figure(slot)
        assert path is not None
        assert resolve_help_asset(path, tree) is not None, slot


def test_tab_figure_slots_live_in_tab_packages_not_host():
    clear_help_figures_cache()
    host_map = Path("src/resources/help/figures.json").read_text(encoding="utf-8")
    assert "workspace.image_compare" not in host_map
    assert "workspace.multi_compare" not in host_map
    assert Path("src/tabs/image_compare/resources/help/figures.json").is_file()
    assert Path("src/tabs/multi_compare/resources/help/figures.json").is_file()
    assert Path("src/tabs/image_compare/resources/help/assets/magnifier.jpg").is_file()
    assert Path("src/tabs/multi_compare/resources/help/assets/layouts.jpg").is_file()
    assert not Path("src/resources/help/assets/image_compare").exists()
    assert not Path("src/resources/help/assets/multi_compare").exists()


def test_comparison_help_interpolates_diff_modes_and_covers_scroll():
    _ensure_image_compare_i18n()
    from tabs.registry import TabRegistry

    TabRegistry().discover()
    TabRegistry().contribute_all_help()
    tree = get_help_tree()
    node = tree.require("workspace.image_compare.comparison")
    md = read_help_page_markdown("ru", node.body, body_root=node.body_root)
    assert "{#scroll-images}" in md
    assert "Скролл по картинкам" in md
    assert "Shift" in md
    out = interpolate_help_markdown(md, "ru")
    assert "Подсветка" in out
    assert "Оттенки серого" in out
    assert "Края" in out
    assert "SSIM" in out
    assert "Highlight" not in out
    assert "Grayscale" not in out
    assert "{{tr:" not in out


def test_magnifier_help_page_uses_ui_labels_not_raw_english_in_ru():
    _ensure_image_compare_i18n()
    from tabs.registry import TabRegistry

    TabRegistry().discover()
    TabRegistry().contribute_all_help()
    tree = get_help_tree()
    node = tree.require("workspace.image_compare.magnifier")
    md = read_help_page_markdown("ru", node.body, body_root=node.body_root)
    out = interpolate_help_markdown(md, "ru")
    assert "Переключить лупу" in out
    assert "Заморозить лупу" in out
    assert "Use Magnifier" not in out
    assert "Freeze Magnifier" not in out
    assert "{{tr:" not in out
    assert "{{img:" not in out
    assert "magnifier.jpg" in out
    assert "image_compare/magnifier.jpg" not in out


def test_help_bodies_use_img_tokens_not_hardcoded_placeholder_paths():
    from plugins.help.tree import host_help_root
    from tabs.registry import TabRegistry

    TabRegistry().discover()
    TabRegistry().contribute_all_help()
    tree = get_help_tree()
    scanned = 0
    for node in tree.nodes.values():
        if node.kind != "page" or not node.body:
            continue
        root = node.body_root if node.body_root is not None else host_help_root()
        for lang in ("en", "ru", "zh", "pt_BR"):
            body = root / lang / node.body
            if not body.is_file():
                continue
            raw = body.read_text(encoding="utf-8")
            scanned += 1
            assert "placeholder.png" not in raw, body
            if "{{img:" in raw:
                rendered = interpolate_help_markdown(raw, lang)
                assert "{{img:" not in rendered, body
    assert scanned >= 40
