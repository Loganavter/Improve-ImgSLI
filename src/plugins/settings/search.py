"""Settings Find Action search index — re-exports host ``ui.actions.search_index``.

Page modules keep ``from plugins.settings.search import group, SearchIndex``.
``SearchGroup.widget`` / tagging live in the host module.
"""

from __future__ import annotations

from ui.actions.search_index import (
    PROP_COMBO_OPTIONS,
    PROP_GROUP,
    PROP_MEMBER,
    SearchGroup,
    SearchIndex,
    group,
)

__all__ = [
    "PROP_COMBO_OPTIONS",
    "PROP_GROUP",
    "PROP_MEMBER",
    "SearchGroup",
    "SearchIndex",
    "group",
]
