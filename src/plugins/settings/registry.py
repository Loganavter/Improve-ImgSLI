"""Settings dialog section registry.

Lets tabs and built-in modules contribute settings sections (sidebar pages).
The dialog enumerates the registry on open and builds every registered
section in order — built-in and tab-owned sections alike. Per-tab sections
are ambient: they are always visible, regardless of the active session, so
tab settings have a permanent home (JetBrains-style plugin settings pages).

A section is a triple of (build, sidebar_item, owner_tab). ``build`` is a
callable ``build(dialog, context) -> None`` that creates a page and adds it
to ``dialog.pages_stack`` (mirroring the existing ``init_*_page`` signatures).
``owner_tab`` is the ``TabContract.session_type`` the section belongs to;
``None`` means the section is platform-owned. ``owner_tab`` is metadata only
— it no longer filters visibility.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from PySide6.QtGui import QIcon

from plugins.settings.search import SearchIndex
from ui.icon_manager import AppIcon

logger = logging.getLogger("ImproveImgSLI")


SectionReader = Callable[[object], dict[str, Any]]
SectionSeeder = Callable[[object], dict[str, Any]]


def _build_key(build: Callable[[object, object], None]) -> object:
    """Stable identity for a section build callable.

    Module-level functions and factory closures (fresh instance per install,
    e.g. ``_make_analysis_section``) compare by ``(module, qualname)``;
    opaque callables fall back to object identity.
    """
    module = getattr(build, "__module__", None)
    qualname = getattr(build, "__qualname__", None)
    if module is not None and qualname is not None:
        return (module, qualname)
    return build


def _same_section_content(a: SettingsSection, b: SettingsSection) -> bool:
    """Content identity for idempotent re-install vs conflicting re-definition.

    Everything semantic is compared; ``icon`` is excluded on purpose —
    factories may build a fresh ``QIcon`` per call (identity-unstable) and
    the icon is decoration, not payload.
    """
    return (
        a.title_key == b.title_key
        and a.owner_tab == b.owner_tab
        and a.order == b.order
        and a.action_description_key == b.action_description_key
        and a.search == b.search
        and _build_key(a.build) == _build_key(b.build)
    )


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


@dataclass(frozen=True, slots=True)
class SettingsSectionExtra:
    """One extra build appended to an existing section (tab-owned perf etc)."""

    section_id: str
    build: Callable[[object, object], None]
    order: int = 100
    search: SearchIndex = field(default_factory=SearchIndex)


@dataclass(frozen=True, slots=True)
class SettingsContribution:
    """Typed, immutable settings fragment owned by one tab.

    ``owner_tab`` must equal the tab's ``i18n_namespace`` per
    ``docs/dev/tabs/isolation.md:60`` (fallback ``session_type``).
    """

    owner_tab: str
    sections: tuple[SettingsSection, ...] = ()
    extras: tuple[SettingsSectionExtra, ...] = ()


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
        for existing in self._sections:
            if existing.section_id != section.section_id:
                continue
            if _same_section_content(existing, section):
                # Idempotent re-install: same payload already registered
                # (startup installs each section up to 3x via per-tab
                # _register_settings + contribute_all_settings broadcasts).
                return
            logger.warning(
                "SettingsRegistry.add: duplicate section_id %r — conflicting "
                "re-definition (owner_tab %r vs %r, build %r vs %r); keeping "
                "the first registration, ignoring the later one",
                section.section_id,
                existing.owner_tab,
                section.owner_tab,
                _build_key(existing.build),
                _build_key(section.build),
            )
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
        # Sections and their extras are ambient — visible regardless of the
        # active session (per-tab settings have a permanent home). The
        # ``active_tab`` parameter is kept for signature compatibility only.
        del active_tab
        extras = self._section_extras.get(section_id, ())
        visible = [(build, order) for build, _owner, order, _search in extras]
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
        """Section search plus all extras (ambient — no active-tab filtering).

        ``active_tab`` is kept for signature compatibility only; tab-owned
        extras (e.g. tab-specific performance groups) are always included
        because per-tab settings have a permanent, always-visible home.
        """
        del active_tab
        index = section.search
        for _build, _owner_tab, _order, extra_search in self._section_extras.get(
            section.section_id, ()
        ):
            index = index.merged(extra_search)
        return index

    def sections_for(self, active_tab: str | None) -> list[SettingsSection]:
        """Every registered section — built-in and tab-owned alike.

        Per-tab sections are ambient: they stay in the sidebar regardless of
        which workspace session is active (JetBrains-style plugin settings).
        ``active_tab`` is kept for signature compatibility only.
        """
        del active_tab
        return sorted(self._sections, key=lambda s: (s.order, s.section_id))

    def all_sections(self) -> list[SettingsSection]:
        return list(self._sections)


_REGISTRY: SettingsRegistry | None = None


def get_settings_registry() -> SettingsRegistry:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = SettingsRegistry()
        _register_builtin_sections(_REGISTRY)
    return _REGISTRY


def install_settings_contributions(
    contributions: list[SettingsContribution],
    registry: SettingsRegistry | None = None,
) -> None:
    """Immutable merge of typed ``SettingsContribution`` fragments.

    Copy-on-install: ``registry.add`` dedupes ``section_id`` and
    ``add_section_extra`` dedupes by ``build`` identity (see
    ``SettingsRegistry.add``). ``owner_tab`` on each contribution must
    match the section/extra's ``owner_tab`` — mismatch is treated as error
    in callers (collectors validate against ``i18n_namespace``).
    """
    target = registry if registry is not None else get_settings_registry()
    for contrib in contributions:
        # Use defensive copies: SettingsRegistry dedupes internally but we
        # ensure we don't mutate the frozen contribution tuples.
        for section in tuple(contrib.sections):
            target.add(section)
        for extra in tuple(contrib.extras):
            target.add_section_extra(
                extra.section_id,
                extra.build,
                owner_tab=contrib.owner_tab,
                order=extra.order,
                search=extra.search,
            )


def ensure_tab_settings_contributions() -> None:
    """Make every registered tab contribute settings sections.

    Contributions are idempotent (``add``/``add_section_extra`` dedupe), so
    this can safely run more than once and after staged discovery: deferred
    tabs (e.g. image_gallery) must not be missed just because platform
    actions or the dialog were first touched during the bootstrap window.

    New path: ``TabRegistry.contribute_all_settings`` gathers typed
    ``SettingsContribution`` return values (per-tab exception logged, not
    stopping others) then ``install_settings_contributions`` merges immutably.
    Legacy ``notify_all("contribute_settings", registry)`` remains as
    fallback for not-yet-migrated tabs (transitional).
    """
    from tabs.registry import TabRegistry

    tabs = TabRegistry()
    # Idempotent per tier — ensures bootstrap AND deferred tabs are
    # registered before contributions are collected.
    tabs.discover()
    # Delegates to TabRegistry which internally uses typed collectors;
    # keeps host -> tabs import limited to tabs.registry (allowed).
    tabs.contribute_all_settings()
    # Transitional fallback: if no typed contributions were installed (all
    # tabs still legacy), fall back to legacy notify_all path — but
    # contribute_all_settings already handles typed vs legacy gracefully.
    # Keeping explicit fallback here is unnecessary; rely on TabRegistry path.


def _register_builtin_sections(registry: SettingsRegistry) -> None:
    from plugins.settings.pages import discover_and_register
    discover_and_register(registry)