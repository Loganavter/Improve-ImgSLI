"""Tab → host help hub presentation (web canon).

Tabs with a multi-page help hub publish a typed ``HelpHubContribution``
collected by ``tabs.use_cases.capability_routing.collect_help_contributions``:
``tab.create_service("contribute_help") -> HelpHubContribution | None``.

Structure (ids, children, bodies) is scanned from the filesystem — the
fragment carries only hub presentation (title/description/icon, translated
through the tab's own i18n pack keys) plus the tab's icon resolver. Tabs
with a single help page (and all plugins) contribute nothing: page titles
come from each page's own ``##`` heading (see ``plugins.help.labels``).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from PySide6.QtGui import QIcon

IconResolver = Callable[[str], QIcon | None]


@dataclass(frozen=True, slots=True)
class HelpHubContribution:
    """Typed, immutable help-hub presentation owned by one tab.

    ``owner_tab`` must equal the tab's ``i18n_namespace`` per
    ``docs/dev/tabs/isolation.md:60`` (fallback ``session_type`` if the tab
    has no explicit i18n namespace). ``mount`` is the scanned hub id
    (``workspace.<tab>`` by convention).
    """

    owner_tab: str
    mount: str
    title: str = ""
    description: str = ""
    icon: str = ""
    title_key: str | None = None
    description_key: str | None = None
    resolve_icon: IconResolver | None = None

    def hub_meta(self) -> dict[str, Any]:
        return {
            "title": self.title or self.mount,
            "description": self.description,
            "icon": self.icon,
            "title_key": self.title_key,
            "description_key": self.description_key,
        }
