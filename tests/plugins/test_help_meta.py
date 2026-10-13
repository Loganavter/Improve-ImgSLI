"""Frontmatter parser for help page cards (``plugins/help/meta.py``)."""

from __future__ import annotations

from plugins.help.meta import PageMeta, parse_page_meta, split_frontmatter
from plugins.help.tree import read_help_page_markdown


def test_body_without_frontmatter_is_returned_verbatim():
    md = "## Title\n\nBody paragraph.\n"
    meta, body = split_frontmatter(md)
    assert meta == PageMeta()
    assert body == md


def test_parses_description_and_icon():
    md = (
        "---\n"
        "description: Short card line\n"
        "icon: settings.svg\n"
        "---\n"
        "## Title\n"
        "\n"
        "Body.\n"
    )
    meta, body = split_frontmatter(md)
    assert meta.description == "Short card line"
    assert meta.icon == "settings.svg"
    assert body == "## Title\n\nBody.\n"


def test_tolerates_missing_and_unknown_keys():
    md = "---\nicon: help.svg\nlegacy: ignored\n---\n## Title\n"
    meta, body = split_frontmatter(md)
    assert meta.description == ""
    assert meta.icon == "help.svg"
    assert body == "## Title\n"


def test_crlf_block_is_parsed_and_stripped():
    md = "---\r\ndescription: A\r\nicon: help.svg\r\n---\r\n## T\r\n\r\nBody.\r\n"
    meta, body = split_frontmatter(md)
    assert meta.description == "A"
    assert meta.icon == "help.svg"
    assert body == "## T\r\n\r\nBody.\r\n"


def test_unterminated_block_is_not_frontmatter():
    md = "---\ndescription: oops\n## Title\n"
    meta, body = split_frontmatter(md)
    assert meta == PageMeta()
    assert body == md


def test_quoted_values_are_unquoted():
    md = '---\ndescription: "Quoted line"\nicon: "settings.svg"\n---\n## T\n'
    meta, _body = split_frontmatter(md)
    assert meta.description == "Quoted line"
    assert meta.icon == "settings.svg"


def test_empty_block_yields_empty_meta():
    md = "---\n---\n## T\n"
    meta, body = split_frontmatter(md)
    assert meta == PageMeta()
    assert body == "## T\n"


def test_parse_page_meta_is_meta_only():
    assert parse_page_meta("## T\n").icon == ""
    assert parse_page_meta("---\nicon: i.svg\n---\n## T\n").icon == "i.svg"


def test_read_help_page_markdown_strips_frontmatter(tmp_path):
    (tmp_path / "en").mkdir()
    (tmp_path / "en" / "x.md").write_text(
        "---\ndescription: A card line\nicon: i.svg\n---\n## T\n\nBody.\n",
        encoding="utf-8",
    )
    md = read_help_page_markdown("en", "x.md", body_root=tmp_path)
    assert md == "## T\n\nBody.\n"
    assert not md.startswith("---")
