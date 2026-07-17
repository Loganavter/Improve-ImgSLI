"""Expand a flyout ``SearchIndex`` into always-listed Find Action rows.

Unlike dialog contribute (live ``widget=`` refs that vanish while hidden),
flyouts use lazy ``ensure_visible`` + ``resolve_widget`` so chrome stays in
the catalog while the panel is closed — same idea as Settings pages.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from core.actions.types import ActionDescriptor, ActionTarget
from ui.actions.dialog_contribute import _run_for_widget
from ui.actions.registry import ActionRegistry, get_action_registry
from ui.actions.search_index import (
    SearchIndex,
    find_tagged_member,
)

logger = logging.getLogger("ImproveImgSLI")


def contribute_flyout_search_actions(
    flyout,
    *,
    index: SearchIndex,
    prefix: str,
    owner_tab: str,
    topic: str,
    breadcrumb: tuple[str, ...],
    show_flyout: Callable[[], None],
    help_page: str | None = None,
    registry: ActionRegistry | None = None,
    include_group_rows: bool = True,
) -> list[str]:
    """Register tagged flyout chrome. Returns registered action ids.

    ``show_flyout`` must open (not toggle-closed) so reveal/run from an
    already-open panel leaves it visible.
    """
    reg = registry if registry is not None else get_action_registry()
    if prefix:
        reg.unregister_prefix(prefix)

    registered: list[str] = []
    missing: list[str] = []

    def _ensure() -> None:
        show_flyout()

    for group_order, group in enumerate(index.groups):
        title_key = group.title_key
        if not title_key:
            continue
        group_breadcrumb = breadcrumb + (title_key,)
        group_action_id = f"{prefix}group.{title_key}"

        if include_group_rows:
            reg.register(
                ActionDescriptor(
                    action_id=group_action_id,
                    label_key=title_key,
                    breadcrumb=breadcrumb,
                    owner_tab=owner_tab,
                    topic=topic,
                    help_page=help_page,
                    sort_key=(group_order, 0),
                    run=_ensure,
                    target=ActionTarget(
                        ensure_visible=_ensure,
                        resolve_widget=lambda f=flyout: f,
                    ),
                )
            )
            registered.append(group_action_id)

        for member_index, member_key in enumerate(group.member_keys):
            widget, combo_index = find_tagged_member(flyout, member_key)
            if widget is None:
                missing.append(member_key)
                continue

            def _resolve_member(
                root=flyout, mkey: str = member_key
            ) -> object | None:
                w, _ = find_tagged_member(root, mkey)
                return w

            activate = _run_for_flyout_member(widget, combo_index=combo_index)

            def _run(
                ensure=_ensure,
                act=activate,
            ) -> None:
                ensure()
                act()

            reg.register(
                ActionDescriptor(
                    action_id=f"{group_action_id}.{member_key}",
                    label_key=member_key,
                    breadcrumb=group_breadcrumb,
                    owner_tab=owner_tab,
                    topic=topic,
                    help_page=help_page,
                    sort_key=(group_order, 1, member_index),
                    run=_run,
                    target=ActionTarget(
                        ensure_visible=_ensure,
                        resolve_widget=_resolve_member,
                    ),
                )
            )
            registered.append(f"{group_action_id}.{member_key}")

    logger.debug(
        "[find-action] flyout contribute prefix=%r registered=%d missing=%s "
        "catalog_total=%d",
        prefix,
        len(registered),
        missing,
        len(reg.all_actions()),
    )
    return registered


def _run_for_flyout_member(
    widget,
    *,
    combo_index: int | None,
) -> Callable[[], None]:
    """Activate a flyout control after the panel is shown.

    Exclusive radios select rather than toggle-off. Sliders / swatches fall
    through to a no-op click when there is nothing useful to activate.
    """
    if combo_index is not None:
        return _run_for_widget(widget, combo_index=combo_index)

    auto_exclusive = getattr(widget, "autoExclusive", None)
    if callable(auto_exclusive) and bool(auto_exclusive()):
        set_checked = getattr(widget, "setChecked", None)
        if callable(set_checked):
            return lambda w=widget: w.setChecked(True)

    is_checkable = getattr(widget, "isCheckable", None)
    if callable(is_checkable) and is_checkable():
        # Toolkit radios often report checkable + exclusive; prefer select.
        set_checked = getattr(widget, "setChecked", None)
        if callable(set_checked) and callable(auto_exclusive):
            return lambda w=widget: w.setChecked(True)

    return _run_for_widget(widget, combo_index=None)
