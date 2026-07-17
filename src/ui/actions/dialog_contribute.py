"""Expand a dialog ``SearchIndex`` into temporary Find Action catalog rows.

Settings keeps its own bridge (lazy resolve + always-listed pages). Dialogs use
this helper: live widget refs, click/toggle/combo/tab ``run``, and
``unregister_prefix`` lifecycle owned by the caller.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from core.actions.types import ActionDescriptor, ActionTarget
from ui.actions.combo_reveal import prepare_combo_option
from ui.actions.registry import ActionRegistry, get_action_registry
from ui.actions.search_index import (
    SearchIndex,
    find_tagged_group,
    find_tagged_member,
)

logger = logging.getLogger("ImproveImgSLI")


def contribute_dialog_search_actions(
    dialog,
    *,
    index: SearchIndex,
    prefix: str,
    owner_tab: str,
    topic: str,
    breadcrumb: tuple[str, ...],
    help_page: str | None = None,
    registry: ActionRegistry | None = None,
    include_group_rows: bool = True,
    shortcuts: dict[str, str] | None = None,
) -> list[str]:
    """Register tagged dialog chrome from ``index``. Returns registered action ids."""
    reg = registry if registry is not None else get_action_registry()
    if prefix:
        reg.unregister_prefix(prefix)
    setattr(dialog, "_find_action_owner_tab", owner_tab)

    shortcut_map = shortcuts or {}
    registered: list[str] = []
    missing: list[str] = []

    for group_order, group in enumerate(index.groups):
        title_key = group.title_key
        if not title_key:
            continue
        group_breadcrumb = breadcrumb + (title_key,)
        group_action_id = f"{prefix}group.{title_key}"

        if include_group_rows:
            group_widget = find_tagged_group(dialog, title_key)
            if group_widget is None:
                # Fall back to first resolvable member for pulse target.
                for member_key in group.member_keys:
                    w, _idx = find_tagged_member(dialog, member_key)
                    if w is not None:
                        group_widget = w
                        break
            reg.register(
                ActionDescriptor(
                    action_id=group_action_id,
                    label_key=title_key,
                    breadcrumb=breadcrumb,
                    owner_tab=owner_tab,
                    topic=topic,
                    help_page=help_page,
                    sort_key=(group_order, 0),
                    run=_noop if group_widget is None else (
                        lambda w=group_widget: _activate_widget(w)
                    ),
                    target=(
                        ActionTarget(widget=group_widget)
                        if group_widget is not None
                        else None
                    ),
                )
            )
            registered.append(group_action_id)

        for member_index, member_key in enumerate(group.member_keys):
            widget, combo_index = find_tagged_member(dialog, member_key)
            if widget is None:
                missing.append(member_key)
                continue
            action_id = f"{group_action_id}.{member_key}"
            run = _run_for_widget(widget, combo_index=combo_index)
            if combo_index is not None:
                # Reveal opens the dropdown focused on the option without
                # committing it; run commits then opens.
                target = ActionTarget(
                    widget=widget,
                    ensure_visible=lambda w=widget, i=combo_index: (
                        prepare_combo_option(w, i, apply=False)
                    ),
                    resolve_widget=lambda w=widget: w,
                )
            else:
                target = ActionTarget(widget=widget)
            reg.register(
                ActionDescriptor(
                    action_id=action_id,
                    label_key=member_key,
                    breadcrumb=group_breadcrumb,
                    owner_tab=owner_tab,
                    topic=topic,
                    help_page=help_page,
                    shortcut=shortcut_map.get(member_key),
                    sort_key=(group_order, 1, member_index),
                    run=run,
                    target=target,
                )
            )
            registered.append(action_id)

    logger.debug(
        "[find-action] dialog contribute prefix=%r registered=%d missing=%s "
        "catalog_total=%d",
        prefix,
        len(registered),
        missing,
        len(reg.all_actions()),
    )
    return registered


def withdraw_dialog_search_actions(
    prefix: str,
    *,
    registry: ActionRegistry | None = None,
) -> None:
    reg = registry if registry is not None else get_action_registry()
    before = len(reg.all_actions())
    if prefix:
        reg.unregister_prefix(prefix)
    logger.debug(
        "[find-action] dialog withdraw prefix=%r catalog %d -> %d",
        prefix,
        before,
        len(reg.all_actions()),
    )


def _noop() -> None:
    return None


def _activate_widget(widget) -> None:
    host = getattr(widget, "_action_search_tab_host", None)
    if host is not None:
        set_current = getattr(host, "setCurrentWidget", None)
        if callable(set_current):
            set_current(widget)
            return
    _click_button(widget)


def _run_for_widget(
    widget,
    *,
    combo_index: int | None,
) -> Callable[[], None]:
    if combo_index is not None:
        return lambda w=widget, i=combo_index: _select_combo_index(w, i)

    host = getattr(widget, "_action_search_tab_host", None)
    if host is not None:
        return lambda h=host, p=widget: _activate_tab(h, p)

    is_checkable = getattr(widget, "isCheckable", None)
    if callable(is_checkable):
        if is_checkable():
            return lambda w=widget: _toggle_button(w)
        return lambda w=widget: _click_button(w)
    if hasattr(widget, "isChecked") and hasattr(widget, "setChecked"):
        # CheckBox-like widgets without isCheckable().
        return lambda w=widget: _toggle_button(w)
    return lambda w=widget: _click_button(w)


def _activate_tab(host, page) -> None:
    set_current = getattr(host, "setCurrentWidget", None)
    if callable(set_current):
        set_current(page)


def _toggle_button(button) -> None:
    if button is None:
        return
    if hasattr(button, "isChecked") and hasattr(button, "setChecked"):
        button.setChecked(not bool(button.isChecked()))
        return
    _click_button(button)


def _click_button(button) -> None:
    if button is None:
        return
    click = getattr(button, "click", None)
    if callable(click):
        click()
        return
    clicked = getattr(button, "clicked", None)
    if clicked is not None and hasattr(clicked, "emit"):
        clicked.emit()


def _select_combo_index(combo, index: int) -> None:
    """Commit ``index`` and open the dropdown (dialog Find Action ``run``)."""
    prepare_combo_option(combo, index, apply=True)
