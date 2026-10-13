"""Localized labels for help tree nodes."""

from __future__ import annotations

import re

from plugins.help.tree import HelpNode
from resources.translations import tr

#: Badge appended to the raw (English) title/description when the requested
#: language has no translation for the node's key. The fallback text is
#: shown (fail-open) but visibly marked so untranslated help is greppable
#: in the UI instead of silently masquerading as translated.
FALLBACK_BADGE = " [en]"

_IMG_TOKEN_RE = re.compile(r"\{\{img:[^}]+\}\}")
_LIST_MARKER_RE = re.compile(r"^(?:[-*+]|\d+[.)])\s+")
#: Inline markdown that must never leak into a plain card subtitle:
#: links, bold/italic, and inline code.
_MD_LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_BOLD_RE = re.compile(r"\*\*([^*]+)\*\*|__([^_]+)__")
_CODE_RE = re.compile(r"`([^`]+)`")


def _strip_inline_markup(text: str) -> str:
    """Drop inline markdown markers so card subtitles stay plain text."""
    text = _MD_LINK_RE.sub(r"\1", text)
    text = _BOLD_RE.sub(lambda match: match.group(1) or match.group(2), text)
    text = _CODE_RE.sub(r"\1", text)
    return text


def _is_translated(text: str | None, key: str | None) -> bool:
    return bool(text) and text != key


def _strip_heading_anchor(text: str) -> str:
    return re.sub(r"\s*\{#[^}]+\}\s*$", "", text).strip()


def _parse_title_desc(markdown: str) -> tuple[str | None, str | None]:
    """Return ``(## heading, first paragraph)`` from a page body."""
    title: str | None = None
    paragraph: list[str] = []
    in_figure = False
    in_fence = False
    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if line.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if line == ":::":
            in_figure = False
            continue
        if line.startswith(":::"):
            in_figure = True
            continue
        if in_figure:
            continue
        if not line:
            if paragraph:
                break
            continue
        if line.startswith(("#", "<!--", "![", "|")):
            if title is None and line.startswith("#"):
                title = _strip_heading_anchor(line.lstrip("#").strip()) or None
            continue
        if title is None:
            continue
        paragraph.append(_LIST_MARKER_RE.sub("", line))
    desc = _strip_inline_markup(_IMG_TOKEN_RE.sub("", " ".join(paragraph))).strip() or None
    return title, desc


_label_cache: dict[tuple[str | None, str | None, str], tuple[str | None, str | None, bool]] = {}


def clear_help_label_cache() -> None:
    _label_cache.clear()


def _page_title_desc(node: HelpNode, language: str) -> tuple[str | None, str | None, bool]:
    """Parse ``(title, description, native)`` from the page's own body.

    ``description`` is the page's leading frontmatter ``description`` (plain
    text) when the *requested language's* body carries one, else its first
    paragraph; both are stripped of inline markup. ``native`` is False when
    the current language has no body file and the English fallback was read
    (callers badge the text, same as untranslated i18n keys).
    """
    from plugins.help.meta import split_frontmatter
    from plugins.help.tree import (
        host_help_root,
        normalize_help_language,
        resolve_help_body_path,
    )

    body_root = node.body_root.as_posix() if node.body_root is not None else None
    key = (body_root, node.body, language)
    cached = _label_cache.get(key)
    if cached is not None:
        return cached
    path = resolve_help_body_path(language, node.body or "", body_root=node.body_root)
    raw = path.read_text(encoding="utf-8") if path.is_file() else ""
    meta, body_md = split_frontmatter(raw)
    title, paragraph = _parse_title_desc(body_md)
    desc = meta.description or paragraph
    native = True
    if node.body and normalize_help_language(language) != "en":
        root = node.body_root if node.body_root is not None else host_help_root()
        native = (root / normalize_help_language(language) / node.body).is_file()
    result = (title, desc, native)
    _label_cache[key] = result
    return result


def node_title(node: HelpNode, language: str) -> str:
    if node.title_key:
        text = tr(node.title_key, language=language)
        if _is_translated(text, node.title_key):
            return text
        if node.title:
            return f"{node.title}{FALLBACK_BADGE}"
    if node.kind == "page" and node.body:
        title, _desc, native = _page_title_desc(node, language)
        if title:
            return title if native or language == "en" else f"{title}{FALLBACK_BADGE}"
    return node.title


def node_description(node: HelpNode, language: str) -> str:
    if node.description_key:
        text = tr(node.description_key, language=language)
        if _is_translated(text, node.description_key):
            return text
        if node.description:
            return f"{node.description}{FALLBACK_BADGE}"
    # Pages: the requested language's frontmatter description (plain text)
    # wins, else its first paragraph. Hubs: the scanned/contributed meta.
    if node.kind == "page" and node.body:
        _title, desc, native = _page_title_desc(node, language)
        if desc:
            return desc if native or language == "en" else f"{desc}{FALLBACK_BADGE}"
    return node.description or ""