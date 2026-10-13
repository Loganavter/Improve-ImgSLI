"""Card subtitles: per-language frontmatter description wins; fallback strips markup."""

from __future__ import annotations

from plugins.help.labels import node_description
from plugins.help.tree import HelpNode


def _page(**kwargs) -> HelpNode:
    base = {"node_id": "demo", "kind": "page", "title": "Demo", "body": "x.md"}
    base.update(kwargs)
    return HelpNode(**base)  # type: ignore[arg-type]


def test_page_frontmatter_description_is_used_per_language(tmp_path):
    (tmp_path / "en").mkdir()
    (tmp_path / "ru").mkdir()
    (tmp_path / "en" / "x.md").write_text(
        "---\ndescription: English card\nicon: i.svg\n---\n## T\n\nBody.\n",
        encoding="utf-8",
    )
    (tmp_path / "ru" / "x.md").write_text(
        "---\ndescription: Русская карточка\nicon: i.svg\n---\n## Т\n\nТекст.\n",
        encoding="utf-8",
    )
    node = _page(body_root=tmp_path)
    # node.description carries the canonical EN block; the label resolves the
    # requested language's own block.
    assert node_description(node, "en") == "English card"
    assert node_description(node, "ru") == "Русская карточка"


def test_fallback_description_strips_inline_markup(tmp_path):
    (tmp_path / "en").mkdir()
    (tmp_path / "en" / "x.md").write_text(
        "## Demo\n\nSee **Image Compare** and `image_compare` in"
        " [Help](help://about).\n",
        encoding="utf-8",
    )
    node = _page(body_root=tmp_path)
    assert node_description(node, "en") == (
        "See Image Compare and image_compare in Help."
    )


def test_missing_body_falls_back_to_node_description(tmp_path):
    node = _page(description="From node", body_root=tmp_path)
    assert node_description(node, "en") == "From node"
