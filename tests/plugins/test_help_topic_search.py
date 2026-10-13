"""Help dialog topic search: ranked title/content matching + navigation."""

from __future__ import annotations

import re

import pytest
from PySide6.QtWidgets import QApplication


def _body_needle(language: str, node_id: str) -> str:
    """A distinctive body word that appears in no node title.

    Deriving the needle from the page keeps the content-match tests honest
    (a content hit, never a title hit) without hardcoding prose that the
    help rewrite may change.
    """
    from plugins.help.tree import get_help_tree, read_help_page_markdown

    tree = get_help_tree()
    node = tree.require(node_id)
    body = read_help_page_markdown(language, node.body, body_root=node.body_root)
    titles = " ".join(n.title.lower() for n in tree.nodes.values())
    for word in re.findall(r"[A-Za-z\u0400-\u04ff]{6,}", body):
        if word.lower() not in titles:
            return word
    raise AssertionError(f"no content-only needle on {node_id}")


def _word_in_page_only(language: str, present_id: str, absent_id: str) -> str:
    """A real word on one page that is absent from another page and all titles.

    Keeps the "phantom match" regression test independent of exact prose:
    the needle is derived from the current bodies instead of being hardcoded.
    """
    from plugins.help.tree import get_help_tree, read_help_page_markdown

    tree = get_help_tree()
    present = tree.require(present_id)
    absent = tree.require(absent_id)
    pbody = read_help_page_markdown(language, present.body, body_root=present.body_root)
    abody = read_help_page_markdown(language, absent.body, body_root=absent.body_root).lower()
    titles = " ".join(n.title.lower() for n in tree.nodes.values())
    for word in re.findall(r"[A-Za-z\u0400-\u04ff]{4,}", pbody):
        low = word.lower()
        if low not in abody and low not in titles:
            return word
    raise AssertionError(f"no word in {present_id} absent from {absent_id}")


@pytest.fixture(scope="module")
def app():
    instance = QApplication.instance() or QApplication([])
    yield instance


@pytest.fixture()
def dialog(app):
    from pathlib import Path

    from resources.translations import add_i18n_root
    from tabs.registry import TabRegistry

    add_i18n_root(Path("src/plugins/help/resources/i18n"))
    registry = TabRegistry()
    registry.discover()
    registry.contribute_all_help()

    from plugins.help.dialog import HelpDialog

    dialog = HelpDialog(current_language="en", app_name="Improve-ImgSLI")
    yield dialog
    dialog.deleteLater()


@pytest.fixture()
def dialog_ru(app):
    from pathlib import Path

    from resources.translations import add_i18n_root
    from tabs.registry import TabRegistry

    add_i18n_root(Path("src/plugins/help/resources/i18n"))
    registry = TabRegistry()
    registry.discover()
    registry.contribute_all_help()

    from plugins.help.dialog import HelpDialog

    dialog = HelpDialog(current_language="ru", app_name="Improve-ImgSLI")
    yield dialog
    dialog.deleteLater()


def test_search_field_is_sidebar_header(dialog):
    # The field is wrapped in a margin host so it keeps window-edge insets
    # inside the flush sidebar column (the shell pins the host, not the
    # field itself, as sidebar_header).
    assert dialog._search_field.parent() is dialog.shell.sidebar_header
    assert dialog._search_field.placeholderText() == "Search help…"


def test_empty_search_keeps_tree_sidebar(dialog):
    assert dialog._search_mode is False
    # At the root hub the sibling tree is empty (pre-existing behavior);
    # the key contract is that no search mode was entered.
    assert dialog._search_field.text() == ""


def test_search_lists_matching_topics_with_icons(dialog):
    dialog._search_field.setText("magnifier")
    dialog._apply_topic_search()
    assert dialog._search_mode is True
    rows = [
        dialog.nav_widget.item(i) for i in range(dialog.nav_widget.count())
    ]
    texts = [item.text().lower() for item in rows]
    assert any("magnifier" in t for t in texts)
    assert all(item.data() for item in rows)
    # Hub + page matches both carry icons (not None) when resolvable.
    assert any(item.data() == "workspace.image_compare.magnifier" for item in rows)


def test_search_matches_page_content_not_only_title(dialog):
    # A word living only in the workspace page body (never in a title) must
    # still surface its page as a content match.
    needle = _body_needle("en", "workspace.session_picker")
    dialog._search_field.setText(needle)
    dialog._apply_topic_search()
    rows = [
        dialog.nav_widget.item(i) for i in range(dialog.nav_widget.count())
    ]
    assert any(item.data() == "workspace.session_picker" for item in rows)


def test_search_does_not_match_topic_descriptions(dialog):
    # "Two-image compare" is the workspace hub description; descriptions are
    # deliberately not indexed (content search covers pages instead).
    dialog._search_field.setText("two-image")
    dialog._apply_topic_search()
    rows = [
        dialog.nav_widget.item(i) for i in range(dialog.nav_widget.count())
    ]
    assert not any(item.data() == "workspace.image_compare" for item in rows)


def test_content_match_requires_real_substring_not_fuzzy_scatter(dialog_ru):
    # A word that lives on the settings page but is NOT a substring of the
    # getting-started page body: the fuzzy matcher's sequence fallback used to
    # scatter the letters across the long page and produce a phantom match that
    # could never be highlighted.
    needle = _word_in_page_only("ru", "platform.settings", "platform.getting_started")
    dialog_ru._search_field.setText(needle)
    dialog_ru._apply_topic_search()
    rows = [
        dialog_ru.nav_widget.item(i) for i in range(dialog_ru.nav_widget.count())
    ]
    assert not any(
        item.data() == "platform.getting_started" for item in rows
    )
    # It IS a real substring of the settings page — that one still matches.
    assert any(item.data() == "platform.settings" for item in rows)


def test_ru_content_match_highlights_real_occurrence(dialog_ru):
    # The reported flow: type "язык", pick "Настройки" — the word must be
    # highlighted on the page (a phantom fuzzy match could not be).
    dialog_ru._search_field.setText("язык")
    dialog_ru._apply_topic_search()
    row_index = next(
        i
        for i in range(dialog_ru.nav_widget.count())
        if dialog_ru.nav_widget.item(i).data() == "platform.settings"
    )
    dialog_ru._on_search_result_activated(row_index)
    canvas = dialog_ru._document._canvas
    rng = canvas._selection.range()
    assert rng is not None
    assert canvas.plain_text()[rng[0] : rng[1]].lower() == "язык"
    assert not canvas._search_marker.isHidden()


def test_activating_content_match_scrolls_and_highlights(dialog):
    needle = _body_needle("en", "workspace.session_picker")
    dialog._search_field.setText(needle)
    dialog._apply_topic_search()
    assert dialog._search_mode is True
    row_index = next(
        i
        for i in range(dialog.nav_widget.count())
        if dialog.nav_widget.item(i).data() == "workspace.session_picker"
    )
    dialog._on_search_result_activated(row_index)
    assert dialog._nav.current_id == "workspace.session_picker"
    # The first occurrence is highlighted via the document selection and the
    # canvas exposes a scroll target for the match.
    canvas = dialog._document._canvas
    rng = canvas._selection.range()
    assert rng is not None
    assert canvas.plain_text()[rng[0] : rng[1]] == needle
    assert canvas._search_marker is not None
    assert not canvas._search_marker.isHidden()


def test_activating_title_match_does_not_highlight(dialog):
    dialog._search_field.setText("magnifier")
    dialog._apply_topic_search()
    row_index = next(
        i
        for i in range(dialog.nav_widget.count())
        if dialog.nav_widget.item(i).data() == "workspace.image_compare.magnifier"
    )
    dialog._on_search_result_activated(row_index)
    assert dialog._nav.current_id == "workspace.image_compare.magnifier"
    # Title match: page opens normally, no content highlight.
    assert dialog._document._canvas._selection.range() is None


def test_activating_result_pushes_topic_and_keeps_results(dialog):
    dialog._search_field.setText("magnifier")
    dialog._apply_topic_search()
    assert dialog._search_mode is True
    row_index = next(
        i
        for i in range(dialog.nav_widget.count())
        if dialog.nav_widget.item(i).data() == "workspace.image_compare.magnifier"
    )
    dialog._on_search_result_activated(row_index)
    assert dialog._nav.current_id == "workspace.image_compare.magnifier"
    # Results stay visible so the user can click another match.
    assert dialog._search_mode is True
    assert dialog.nav_widget.count() > 1


def test_clear_search_restores_sibling_tree(dialog):
    dialog._search_field.setText("magnifier")
    dialog._apply_topic_search()
    assert dialog._search_mode is True
    row_index = next(
        i
        for i in range(dialog.nav_widget.count())
        if dialog.nav_widget.item(i).data() == "workspace.image_compare.magnifier"
    )
    dialog._on_search_result_activated(row_index)
    dialog.clear_topic_search()
    assert dialog._search_mode is False
    # Back to the sibling tree of the opened page (the image_compare hub's
    # children).
    assert dialog.nav_widget.count() > 0


def test_no_results_shows_placeholder_row(dialog):
    # Ten z's cannot scatter across any page body (unlike a short word).
    dialog._search_field.setText("zzzzzzzzzz")
    dialog._apply_topic_search()
    assert dialog._search_mode is True
    assert dialog.nav_widget.count() == 1
    assert dialog.nav_widget.item(0).data() is None


def test_language_change_reruns_live_search(dialog):
    dialog._search_field.setText("magnifier")
    dialog._apply_topic_search()
    assert dialog._search_mode is True
    dialog.update_language("ru")
    rows = [
        dialog.nav_widget.item(i) for i in range(dialog.nav_widget.count())
    ]
    assert rows
    # The query is language-agnostic (matched via English haystack), rows are
    # re-rendered in the new language (RU titles).
    assert any("луп" in r.text().lower() for r in rows)