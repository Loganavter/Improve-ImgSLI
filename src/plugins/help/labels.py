"""Localized labels for help tree nodes."""

from __future__ import annotations

from plugins.help.tree import HelpNode
from resources.translations import tr


def node_title(node: HelpNode, language: str) -> str:
    if node.title_key:
        text = tr(node.title_key, language=language)
        if text and text != node.title_key:
            return text
    return node.title


def node_description(node: HelpNode, language: str) -> str:
    if node.description_key:
        text = tr(node.description_key, language=language)
        if text and text != node.description_key:
            return text
    return node.description or ""
