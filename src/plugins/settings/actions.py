"""Auto-contribute Settings chrome into the Find Action catalog.

Single entry point: ``SearchIndex`` / ``SearchGroup`` on each
``SettingsSection`` (plus ``add_section_extra`` indexes) become catalog rows.
Pages do not hand-register actions — declare groups once, contribute here.
"""

from __future__ import annotations

from collections.abc import Callable

from core.actions.types import ActionDescriptor, ActionTarget
from plugins.settings.registry import (
    SettingsSection,
    ensure_tab_settings_contributions,
    get_settings_registry,
)
from plugins.settings.search import SearchGroup
from ui.actions.registry import ActionRegistry, get_action_registry

_BC_SETTINGS = "menu.settings"


def contribute_settings_actions(
    *,
    show_settings_section: Callable[[str], None],
    registry: ActionRegistry | None = None,
    resolve_settings_sidebar: Callable[[str], object | None] | None = None,
    resolve_settings_group: Callable[[str, str], object | None] | None = None,
    resolve_settings_member: Callable[[str, str, str], object | None] | None = None,
    run_settings_member: Callable[[str, str, str], None] | None = None,
) -> None:
    """Mirror every Settings page + chrome slot into ``ActionRegistry``.

    - ``settings.page.<section_id>`` — sidebar page (jump + pulse row, always
      listed).
    - ``settings.group.<section_id>.<title_key>`` — fieldset slot (always
      listed; matched by its own title only).
    - ``settings.group.<section_id>.<title_key>.<member_key>`` — one row per
      control inside the fieldset (e.g. "Vulkan", "Светлая"), always listed
      so the empty palette is browsable, not just searchable. A query hits
      the control by its own name instead of surfacing the generic group row
      it lives in (e.g. `vulkan` → "Vulkan", not "Render backend").
      Enter runs the control (apply without showing Settings); reveal opens
      and pulses. Tab extras keep ``owner_tab``.
    """
    ensure_tab_settings_contributions()
    settings_reg = get_settings_registry()
    reg = registry if registry is not None else get_action_registry()

    for section in settings_reg.all_sections():
        _register_page(
            reg,
            section,
            show_settings_section=show_settings_section,
            resolve_settings_sidebar=resolve_settings_sidebar,
        )
        # ``group_order`` numbers every group under this page (built-in, then
        # tab extras) so the empty palette can lay them out directly, without
        # the sort key needing to parse the action id back apart.
        group_order = 0
        for group in section.search.groups:
            _register_group(
                reg,
                section=section,
                owner_tab=section.owner_tab,
                group=group,
                group_order=group_order,
                show_settings_section=show_settings_section,
                resolve_settings_group=resolve_settings_group,
                resolve_settings_member=resolve_settings_member,
                run_settings_member=run_settings_member,
            )
            group_order += 1
        for owner_tab, extra_search in settings_reg.iter_extra_searches(
            section.section_id
        ):
            for group in extra_search.groups:
                _register_group(
                    reg,
                    section=section,
                    owner_tab=(
                        owner_tab if owner_tab is not None else section.owner_tab
                    ),
                    group=group,
                    group_order=group_order,
                    show_settings_section=show_settings_section,
                    resolve_settings_group=resolve_settings_group,
                    resolve_settings_member=resolve_settings_member,
                    run_settings_member=run_settings_member,
                )
                group_order += 1


def _register_page(
    reg: ActionRegistry,
    section: SettingsSection,
    *,
    show_settings_section: Callable[[str], None],
    resolve_settings_sidebar: Callable[[str], object | None] | None,
) -> None:
    section_id = section.section_id

    def _ensure(sid: str = section_id) -> None:
        show_settings_section(sid)

    resolve = None
    if resolve_settings_sidebar is not None:
        def _resolve(sid: str = section_id) -> object | None:
            return resolve_settings_sidebar(sid)

        resolve = _resolve

    # Page row is navigation only — member chrome lives on group slots so the
    # empty palette shows «Язык» / «Шрифт» without requiring a search query.
    reg.register(
        ActionDescriptor(
            action_id=f"settings.page.{section_id}",
            label_key=section.title_key,
            description_key=(
                section.action_description_key or "action.settings.page_desc"
            ),
            breadcrumb=(_BC_SETTINGS, section.title_key),
            owner_tab=section.owner_tab,
            topic="settings",
            help_page="settings",
            sort_key=(section.order, 0),
            run=_ensure,
            target=ActionTarget(ensure_visible=_ensure, resolve_widget=resolve),
        )
    )


def _register_group(
    reg: ActionRegistry,
    *,
    section: SettingsSection,
    owner_tab: str | None,
    group: SearchGroup,
    group_order: int,
    show_settings_section: Callable[[str], None],
    resolve_settings_group: Callable[[str, str], object | None] | None,
    resolve_settings_member: Callable[[str, str, str], object | None] | None,
    run_settings_member: Callable[[str, str, str], None] | None,
) -> None:
    title_key = group.title_key
    if not title_key:
        return
    section_id = section.section_id
    group_action_id = f"settings.group.{section_id}.{title_key}"
    breadcrumb = (_BC_SETTINGS, section.title_key, title_key)

    def _ensure(sid: str = section_id) -> None:
        show_settings_section(sid)

    resolve_group = None
    if resolve_settings_group is not None:
        def _resolve_group(sid: str = section_id, gkey: str = title_key) -> object | None:
            return resolve_settings_group(sid, gkey)

        resolve_group = _resolve_group

    # Group row pulses the fieldset; member rows pulse the tagged control inside it.
    group_target = ActionTarget(ensure_visible=_ensure, resolve_widget=resolve_group)

    # The group row — browsable in the empty palette, matched only by its own
    # title. A query like "vulkan" should surface the concrete option below,
    # not this generic "render backend" row.
    reg.register(
        ActionDescriptor(
            action_id=group_action_id,
            label_key=title_key,
            description_key="action.settings.group_desc",
            breadcrumb=breadcrumb,
            owner_tab=owner_tab,
            topic="settings",
            help_page="settings",
            sort_key=(section.order, 1, group_order, 0),
            run=_ensure,
            target=group_target,
        )
    )

    # One row per control inside the fieldset — browsable right under its
    # group, shown by its own name ("Vulkan", "Светлая") with the group title
    # kept in the breadcrumb instead of the group's generic label.
    for member_index, member_key in enumerate(group.member_keys):
        resolve_member = None
        if resolve_settings_member is not None:
            def _resolve_member(
                sid: str = section_id,
                gkey: str = title_key,
                mkey: str = member_key,
            ) -> object | None:
                return resolve_settings_member(sid, gkey, mkey)

            resolve_member = _resolve_member
        elif resolve_group is not None:
            resolve_member = resolve_group

        if run_settings_member is not None:
            def _run_member(
                sid: str = section_id,
                gkey: str = title_key,
                mkey: str = member_key,
            ) -> None:
                run_settings_member(sid, gkey, mkey)

            member_run = _run_member
        else:
            member_run = _ensure

        member_target = ActionTarget(
            ensure_visible=_ensure,
            resolve_widget=resolve_member,
        )
        reg.register(
            ActionDescriptor(
                action_id=f"{group_action_id}.{member_key}",
                label_key=member_key,
                description_key="action.settings.slot_desc",
                breadcrumb=breadcrumb,
                owner_tab=owner_tab,
                topic="settings",
                help_page="settings",
                sort_key=(section.order, 1, group_order, 1, member_index),
                run=member_run,
                target=member_target,
            )
        )
