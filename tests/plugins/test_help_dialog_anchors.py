"""Markdown help dialog anchors: strip ``{#id}`` heading suffixes, inject
missing heading anchors, and build a markdown TOC for pages with ≥2 ``###``
sections.

Dogma source: docs/dev/HELP_SYSTEM.md (anchor + TOC contract).

The toolkit help pipeline moved from HTML (``QTextBrowser``) to painted
markdown (``TextView``): ``ensure_heading_ids`` → ``inject_heading_anchors``
and ``build_page_toc`` → ``build_toc_markdown``, both operating on markdown
text instead of HTML.
"""

from __future__ import annotations

from sli_ui_toolkit.ui.widgets.composite.markdown_help_dialog import (
    build_toc_markdown,
    inject_heading_anchors,
    strip_heading_attr_suffix,
)


def test_strip_heading_attr_suffix_removes_anchor_marker():
    assert strip_heading_attr_suffix("Settings {#settings}") == "Settings"


def test_inject_heading_anchors_keeps_existing_and_slugifies_missing():
    md = (
        "# Title\n\n"
        "### Quick Save\n\n"
        "### Quick  Save\n\n"
        "#### Explicit {#kept-id}\n"
    )

    result = inject_heading_anchors(md, fallback_prefix="export")

    assert "#### Explicit {#kept-id}" in result  # existing anchor untouched
    assert "### Quick Save {#quick-save}" in result
    assert "### Quick  Save {#quick-save-2}" in result  # deduplicated


def test_build_toc_markdown_creates_internal_links_for_h3_sections():
    md = (
        "### Saving An Image {#saving-an-image}\n\n"
        "Body.\n\n"
        "### Quick Save {#quick-save}\n"
    )

    toc = build_toc_markdown(md, title="On this page")

    assert "[Saving An Image](#saving-an-image)" in toc
    assert "[Quick Save](#quick-save)" in toc
    assert "On this page" in toc


def test_build_toc_markdown_empty_below_two_h3():
    md = "### Only One {#only-one}\n\nBody.\n"
    assert build_toc_markdown(md, title="On this page") == ""
