"""Help markdown ``{{tr:…}}`` interpolation against UI i18n packs."""

from __future__ import annotations

from pathlib import Path

from plugins.help.interpolate import interpolate_help_markdown
from plugins.help.tree import get_help_tree, read_help_page_markdown
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
