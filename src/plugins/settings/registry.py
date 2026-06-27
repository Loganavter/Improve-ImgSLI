"""Settings dialog section registry.

Lets tabs and built-in modules contribute settings sections (sidebar pages).
The dialog enumerates the registry on open, filters sections by the active
tab's session_type, and builds each visible section in order.

A section is a triple of (build, sidebar_item, owner_tab). ``build`` is a
callable ``build(dialog, context) -> None`` that creates a page and adds it
to ``dialog.pages_stack`` (mirroring the existing ``init_*_page`` signatures).
``owner_tab`` is the ``TabContract.session_type`` the section belongs to;
``None`` means the section is always visible regardless of active tab.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from ui.icon_manager import AppIcon


@dataclass(frozen=True)
class SettingsSection:
    section_id: str
    title_key: str
    icon: AppIcon
    build: Callable[[object, object], None]
    owner_tab: Optional[str] = None
    order: int = 100


class SettingsRegistry:
    def __init__(self) -> None:
        self._sections: list[SettingsSection] = []
        self._section_extras: dict[
            str, list[tuple[Callable[[object, object], None], str | None, int]]
        ] = {}

    def add(self, section: SettingsSection) -> None:
        if any(s.section_id == section.section_id for s in self._sections):
            return
        self._sections.append(section)

    def remove(self, section_id: str) -> None:
        self._sections = [s for s in self._sections if s.section_id != section_id]

    def add_section_extra(
        self,
        section_id: str,
        build: Callable[[object, object], None],
        *,
        owner_tab: str | None = None,
        order: int = 100,
    ) -> None:
        extras = self._section_extras.setdefault(section_id, [])
        if any(existing is build for existing, _owner, _order in extras):
            return
        extras.append((build, owner_tab, order))

    def extras_for(
        self,
        section_id: str,
        active_tab: str | None,
    ) -> list[Callable[[object, object], None]]:
        extras = self._section_extras.get(section_id, ())
        visible = [
            (build, order)
            for build, owner_tab, order in extras
            if owner_tab is None or owner_tab == active_tab
        ]
        return [build for build, _order in sorted(visible, key=lambda item: item[1])]

    def sections_for(self, active_tab: str | None) -> list[SettingsSection]:
        visible = [s for s in self._sections if s.owner_tab is None or s.owner_tab == active_tab]
        return sorted(visible, key=lambda s: (s.order, s.section_id))

    def all_sections(self) -> list[SettingsSection]:
        return list(self._sections)


_REGISTRY: SettingsRegistry | None = None
_TAB_CONTRIBUTIONS_LOADED = False


def get_settings_registry() -> SettingsRegistry:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = SettingsRegistry()
        _register_builtin_sections(_REGISTRY)
    return _REGISTRY


def ensure_tab_settings_contributions() -> None:
    global _TAB_CONTRIBUTIONS_LOADED
    if _TAB_CONTRIBUTIONS_LOADED:
        return
    _TAB_CONTRIBUTIONS_LOADED = True
    registry = get_settings_registry()
    try:
        from tabs.registry import TabRegistry

        tabs = TabRegistry()
        tabs.discover()
        for tab in tabs.list_tabs():
            tab.contribute_settings(registry)
    except Exception:
        import logging

        logging.getLogger("ImproveImgSLI").exception(
            "Failed to load tab settings contributions"
        )


def _register_builtin_sections(registry: SettingsRegistry) -> None:
    from plugins.settings.pages import discover_and_register
    discover_and_register(registry)
