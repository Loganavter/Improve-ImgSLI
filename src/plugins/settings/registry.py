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

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from PySide6.QtGui import QIcon

from plugins.settings.search import SearchIndex
from ui.icon_manager import AppIcon


SectionReader = Callable[[object], dict[str, Any]]
SectionSeeder = Callable[[object], dict[str, Any]]


@dataclass(frozen=True)
class SettingsSection:
    section_id: str
    title_key: str
    icon: AppIcon | QIcon
    build: Callable[[object, object], None]
    owner_tab: Optional[str] = None
    order: int = 100
    # Single source of truth for Find Action chrome (groups + keys).
    search: SearchIndex = field(default_factory=SearchIndex)
    # Optional Find Action description (defaults to generic page_desc).
    action_description_key: str | None = None

    @property
    def search_keys(self) -> tuple[str, ...]:
        return self.search.keys


class SettingsRegistry:
    def __init__(self) -> None:
        self._sections: list[SettingsSection] = []
        self._section_extras: dict[
            str,
            list[
                tuple[
                    Callable[[object, object], None],
                    str | None,
                    int,
                    SearchIndex,
                ]
            ],
        ] = {}
        self._payload_readers: dict[str, SectionReader] = {}
        self._payload_seeders: dict[str, SectionSeeder] = {}

    def register_payload_reader(self, section_id: str, reader: SectionReader) -> None:
        self._payload_readers[section_id] = reader

    def register_payload_seeder(self, section_id: str, seeder: SectionSeeder) -> None:
        self._payload_seeders[section_id] = seeder

    def read_payloads(self, dialog: object) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for section_id, reader in self._payload_readers.items():
            try:
                values = reader(dialog)
            except Exception:
                import logging
                logging.getLogger("ImproveImgSLI").exception(
                    "Settings payload reader failed for section %s", section_id
                )
                continue
            if values:
                out[section_id] = dict(values)
        return out

    def seed_payloads(self, source: object) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for section_id, seeder in self._payload_seeders.items():
            try:
                values = seeder(source)
            except Exception:
                import logging
                logging.getLogger("ImproveImgSLI").exception(
                    "Settings payload seeder failed for section %s", section_id
                )
                continue
            if values:
                out[section_id] = dict(values)
        return out

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
        search: SearchIndex | None = None,
    ) -> None:
        extras = self._section_extras.setdefault(section_id, [])
        if any(existing is build for existing, _owner, _order, _search in extras):
            return
        extras.append((build, owner_tab, order, search or SearchIndex()))

    def extras_for(
        self,
        section_id: str,
        active_tab: str | None,
    ) -> list[Callable[[object, object], None]]:
        extras = self._section_extras.get(section_id, ())
        visible = [
            (build, order)
            for build, owner_tab, order, _search in extras
            if owner_tab is None or owner_tab == active_tab
        ]
        return [build for build, _order in sorted(visible, key=lambda item: item[1])]

    def iter_extra_searches(
        self,
        section_id: str,
    ) -> list[tuple[str | None, SearchIndex]]:
        """``(owner_tab, search)`` for every extra on ``section_id``."""
        return [
            (owner_tab, extra_search)
            for _build, owner_tab, _order, extra_search in self._section_extras.get(
                section_id, ()
            )
        ]

    def search_for(
        self,
        section: SettingsSection,
        *,
        active_tab: str | None = None,
    ) -> SearchIndex:
        """Section search plus extras visible for ``active_tab``.

        Tab-owned extras (e.g. image_compare performance groups) are omitted
        when the active session cannot show them in Settings.
        """
        index = section.search
        for _build, owner_tab, _order, extra_search in self._section_extras.get(
            section.section_id, ()
        ):
            if owner_tab is not None and owner_tab != active_tab:
                continue
            index = index.merged(extra_search)
        return index

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
        from tabs.registry import TabRegistry, get_shared_tab_registry

        tabs = get_shared_tab_registry()
        if not tabs.list_tabs():
            tabs = TabRegistry()
            tabs.discover()
        tabs.notify_all("contribute_settings", registry)
    except Exception:
        import logging

        logging.getLogger("ImproveImgSLI").exception(
            "Failed to load tab settings contributions"
        )


def _register_builtin_sections(registry: SettingsRegistry) -> None:
    from plugins.settings.pages import discover_and_register
    discover_and_register(registry)
