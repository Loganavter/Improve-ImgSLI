"""Help body integrity: literal on-screen labels and body-relative images.

Help bodies carry literal labels now (the ``{{tr:…}}`` interpolation layer was
removed) — content is authored per language, so there is no runtime key lookup
and no i18n placeholder may survive in a body.
"""

from __future__ import annotations

import re
from pathlib import Path

from plugins.help.tree import (
    get_help_tree,
    host_help_root,
    read_help_page_markdown,
    resolve_help_asset,
)

_IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)\s]+)\)")


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


def test_help_bodies_carry_no_i18n_placeholders():
    """A leaked ``{{tr:…}}`` renders as a raw token — it must never ship."""
    scanned = 0
    for body in _iter_bodies():
        scanned += 1
        raw = body.read_text(encoding="utf-8")
        assert "{{tr:" not in raw, body
    assert scanned >= 40


def test_read_help_page_markdown_returns_body_verbatim():
    from tabs.registry import TabRegistry

    TabRegistry().discover()
    TabRegistry().contribute_all_help()
    tree = get_help_tree()
    node = tree.require("workspace.image_compare.comparison")
    md = read_help_page_markdown("ru", node.body, body_root=node.body_root)
    assert md == (node.body_root / "ru" / node.body).read_text(encoding="utf-8")
    assert "{#scroll-images}" in md
    assert "{{tr:" not in md


def test_resolve_help_asset_uses_rendered_body_file():
    body = Path("src/resources/help/en/ui/buttons.md")
    resolved = resolve_help_asset("../../assets/ui/toolbar.jpg", body)
    assert resolved is not None and resolved.is_file()
    assert resolve_help_asset("../../assets/ui/toolbar.jpg", None) is None
    assert resolve_help_asset("../../assets/nope.jpg", body) is None
