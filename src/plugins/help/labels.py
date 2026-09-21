"""Localized labels for help tree nodes."""

from __future__ import annotations

from plugins.help.tree import HelpNode
from resources.translations import tr

#: Badge appended to the raw (English) title/description when the requested
#: language has no translation for the node's key. The fallback text is
#: shown (fail-open) but visibly marked so untranslated help is greppable
#: in the UI instead of silently masquerading as translated.
FALLBACK_BADGE = " [en]"


def _is_translated(text: str | None, key: str | None) -> bool:
    return bool(text) and text != key


def node_title(node: HelpNode, language: str) -> str:
    if node.title_key:
        text = tr(node.title_key, language=language)
        if _is_translated(text, node.title_key):
            return text
        if node.title:
            return f"{node.title}{FALLBACK_BADGE}"
    return node.title


def node_description(node: HelpNode, language: str) -> str:
    if node.description_key:
        text = tr(node.description_key, language=language)
        if _is_translated(text, node.description_key):
            return text
        if node.description:
            return f"{node.description}{FALLBACK_BADGE}"
    return node.description or ""