"""Help markdown ``{{tr:…}}`` interpolation and body-relative images."""

from __future__ import annotations

import re
from pathlib import Path

from plugins.help.interpolate import interpolate_help_markdown
from plugins.help.tree import (
    get_help_tree,
    host_help_root,
    read_help_page_markdown,
    resolve_help_asset,
)
from resources.translations import add_i18n_root

_IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)\s]+)\)")


def _ensure_image_compare_i18n() -> None:
    add_i18n_root(Path("src/tabs/image_compare/resources/i18n"))


def _help_package_of(body: Path) -> Path:
    """Nearest ``resources/help`` ancestor owning ``body``."""
    for parent in body.parents:
        if parent.name == "help" and parent.parent.name == "resources":
            return parent
    raise AssertionError(f"body outside a help package: {body}")


def _iter_bodies():
    from tabs.registry import TabRegistry

    TabRegistry().discover()
    TabRegistry().contribute_all_help()
    tree = get_help_tree()
    for node in tree.nodes.values():
        if node.kind != "page" or not node.body:
            continue
        root = node.body_root if node.body_root is not None else host_help_root()
        for lang in ("en", "ru", "zh", "pt_BR"):
            body = root / lang / node.body
            if body.is_file():
                yield body


def test_interpolate_help_markdown_resolves_tab_action_keys():
    _ensure_image_compare_i18n()
    text = "Click **{{tr:image_compare.action.magnifier}}** or `M`."
    ru = interpolate_help_markdown(text, "ru")
    en = interpolate_help_markdown(text, "en")
    assert "Переключить лупу" in ru
    assert "{{tr:" not in ru
    assert "Toggle Magnifier" in en


def test_body_relative_images_exist_inside_own_package():
    scanned = 0
    images = 0
    for body in _iter_bodies():
        scanned += 1
        pkg = _help_package_of(body)
        raw = body.read_text(encoding="utf-8")
        assert "placeholder.png" not in raw, body
        assert "{{img:" not in raw, body
        for target in _IMAGE_RE.findall(raw):
            if target.startswith(("http://", "https://", "#", "help://")):
                continue
            resolved = (body.parent / target).resolve()
            assert resolved.is_file(), (body, target)
            resolved.relative_to(pkg.resolve())
            images += 1
    assert scanned >= 40
    assert images >= 20


def test_resolve_help_asset_uses_rendered_body_file():
    body = Path("src/resources/help/en/ui/buttons.md")
    resolved = resolve_help_asset("../../assets/ui/toolbar.jpg", body)
    assert resolved is not None and resolved.is_file()
    assert resolve_help_asset("../../assets/ui/toolbar.jpg", None) is None
    assert resolve_help_asset("../../assets/nope.jpg", body) is None


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
