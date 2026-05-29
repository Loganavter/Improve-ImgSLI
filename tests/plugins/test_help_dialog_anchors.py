"""Markdown help dialog anchors: strip ``{#id}`` heading suffixes, generate
missing heading ids, and build an internal-link TOC for h3 sections.

Dogma source: docs/dev/HELP_WIDGET.md.
"""

from sli_ui_toolkit.ui.widgets.composite.markdown_help_dialog import (
    build_page_toc,
    ensure_heading_ids,
    strip_heading_attr_suffix,
)

def test_strip_heading_attr_suffix_removes_anchor_marker():
    assert strip_heading_attr_suffix("Settings {#settings}") == "Settings"

def test_ensure_heading_ids_keeps_existing_ids_and_generates_missing_ones():
    html = (
        '<h3 id="kept-id">Existing</h3>'
        '<h3>Quick Save</h3>'
        '<h3>Quick Save</h3>'
    )

    result = ensure_heading_ids(html, fallback_prefix="export")

    assert 'id="kept-id"' in result
    assert 'id="quick-save"' in result
    assert 'id="quick-save-2"' in result

def test_build_page_toc_creates_internal_links_for_h3_sections():
    html = (
        '<h3 id="saving-an-image">Saving An Image</h3>'
        '<p>Body</p>'
        '<h3 id="quick-save">Quick Save</h3>'
    )

    toc = build_page_toc(html, title="On this page")

    assert 'href="#saving-an-image"' in toc
    assert 'href="#quick-save"' in toc
    assert "On this page" in toc
