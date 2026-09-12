"""Help dialog topic search: title + page-content ranking.

Split out of ``plugins/help/dialog.py`` per the "thin owner + use_cases/
module" pattern in ``docs/dev/CODE_PATTERNS.md`` — plain functions taking the
dialog as first argument, same shape as
``plugins/settings/dialog_search.py``.
"""

from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut

from plugins.help.icons import resolve_help_icon
from plugins.help.labels import node_title
from plugins.help.tree import read_help_page_markdown
from resources.translations import tr
from sli_ui_toolkit.managers import scaled_px
from sli_ui_toolkit.ui.widgets.composite.help_document import (
    blocks_to_plain_text,
    parse_help_blocks,
)


@lru_cache(maxsize=512)
def _page_search_text(language: str, body_rel: str, body_root) -> str:
    """Cached plain text of a help page body (what the canvas renders).

    Mirrors ``HelpDocumentView`` block parsing so the search haystack is
    exactly the text ``scroll_to_text`` can highlight afterwards.
    """
    md = read_help_page_markdown(language, body_rel, body_root=body_root)
    return blocks_to_plain_text(parse_help_blocks(md))


@lru_cache(maxsize=512)
def _page_search_norm_text(language: str, body_rel: str, body_root) -> str:
    """Cached normalized page text — the haystack for content hits.

    ``match_score_normalized`` is non-fuzzy by default (exact/prefix/
    substring only), so only real locatable occurrences rank for content
    matches — the canvas can always highlight them.
    """
    from sli_ui_toolkit.ui.widgets.comboboxes._search import normalize_for_search

    return normalize_for_search(_page_search_text(language, body_rel, body_root))


def _setup_topic_search(dialog) -> None:
    dialog._search_timer = QTimer(dialog)
    dialog._search_timer.setSingleShot(True)
    dialog._search_timer.setInterval(120)
    dialog._search_timer.timeout.connect(dialog._apply_topic_search)
    dialog._search_field.textChanged.connect(dialog._on_search_text_changed)
    dialog._search_escape = QShortcut(
        QKeySequence(Qt.Key.Key_Escape), dialog._search_field
    )
    dialog._search_escape.activated.connect(dialog.clear_topic_search)


def _on_search_text_changed(dialog, _text: str) -> None:
    if dialog._search_timer.isActive():
        dialog._search_timer.stop()
    dialog._search_timer.start()


def _apply_topic_search(dialog) -> None:
    query = dialog._search_field.text().strip()
    if not query:
        dialog.clear_topic_search()
        return
    matches = dialog._rank_topic_matches(query)
    dialog._search_mode = True
    #: node ids whose best match came from page content (vs title) — those
    #: results open at the first occurrence with a text highlight.
    dialog._search_body_match_ids = {
        node_id for node_id, _score, in_body in matches if in_body
    }
    dialog.nav_widget.clear()
    if not matches:
        dialog.nav_widget.add_item(
            tr("help.search_no_results", language=dialog.current_language),
            row_height=scaled_px(35),
        )
        dialog._set_sidebar_expanded(True)
        return
    for node_id, _score, _in_body in matches[:12]:
        node = dialog._tree.require(node_id)
        dialog.nav_widget.add_item(
            node_title(node, dialog.current_language),
            icon=resolve_help_icon(
                node.icon, resolvers=dialog._tree.icon_resolvers
            ),
            data=node_id,
            row_height=scaled_px(35),
        )
    dialog._set_sidebar_expanded(True)
    dialog.nav_widget.setCurrentRow(-1)


def _rank_topic_matches(dialog, query: str) -> list[tuple[str, int, bool]]:
    from sli_ui_toolkit.ui.widgets.comboboxes._search import (
        match_score_normalized,
        normalize_for_search,
    )

    # Match against the current language AND English (Find Action-style
    # cross-language haystacks): a query typed before a language switch —
    # or in a language the topic isn't translated into — still hits.
    langs = (
        ("en", dialog.current_language)
        if dialog.current_language != "en"
        else ("en",)
    )
    norm_query = normalize_for_search(query)
    scored: list[tuple[int, str, bool]] = []
    for node_id, node in dialog._tree.nodes.items():
        if node_id == dialog._tree.root_id:
            continue
        best: int | None = None
        in_body = False
        for lang in langs:
            title = node_title(node, lang)
            if title:
                score = match_score_normalized(
                    norm_query, normalize_for_search(title)
                )
                if score is not None and (best is None or score < best):
                    best = score
                    in_body = False
            if node.kind == "page" and node.body:
                # Non-fuzzy by default: only real locatable occurrences
                # rank for content matches, so the canvas can always
                # scroll to and highlight them.
                norm_body = _page_search_norm_text(
                    lang, node.body, node.body_root
                )
                score = match_score_normalized(norm_query, norm_body)
                if score is not None and (best is None or score < best):
                    best = score
                    in_body = True
        if best is not None:
            scored.append((best, node_id, in_body))
    scored.sort(key=lambda item: (item[0], item[1]))
    return [(node_id, score, in_body) for score, node_id, in_body in scored]


def _on_search_result_activated(dialog, row: int) -> None:
    item = dialog.nav_widget.item(row)
    if item is None:
        return
    node_id = item.data()
    if not node_id:
        return
    dialog._pending_anchor = None
    dialog._nav.push(node_id)
    dialog._render_current()
    # Content matches jump to the first occurrence and highlight it;
    # title matches just open the page normally.
    if node_id in getattr(dialog, "_search_body_match_ids", ()):
        query = dialog._search_field.text().strip()
        if query:
            target = dialog._document.scroll_to_text(query)
            if target is not None:
                dialog._scroll.ensureWidgetVisible(target, 0, 24)


def clear_topic_search(dialog) -> None:
    if not dialog._search_mode:
        return
    dialog._search_mode = False
    if dialog._search_field.text():
        dialog._search_field.blockSignals(True)
        dialog._search_field.clear()
        dialog._search_field.blockSignals(False)
    dialog._sync_sidebar()
