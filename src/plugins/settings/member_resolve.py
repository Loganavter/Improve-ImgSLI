"""Resolve Find Action member chrome inside a Settings page (or any tagged tree)."""

from __future__ import annotations

from PySide6.QtWidgets import QScrollArea, QWidget

from ui.actions.combo_reveal import prepare_combo_option
from ui.actions.search_index import (
    PROP_COMBO_OPTIONS,
    PROP_MEMBER,
    combo_option_map,
    find_tagged_member,
)


def scroll_widget_into_view(widget: QWidget) -> None:
    """Scroll the nearest page ``QScrollArea`` so ``widget`` is visible."""
    parent = widget.parentWidget()
    while parent is not None:
        if isinstance(parent, QScrollArea):
            parent.ensureWidgetVisible(widget, 0, 24)
            return
        parent = parent.parentWidget()


def _prepare_combo_option(combo: QWidget, member_key: str, index: int) -> QWidget:
    """Open the dropdown focused on the option without changing the field value."""
    _ = member_key
    return prepare_combo_option(combo, index, apply=False)  # type: ignore[return-value]


def activate_member_control(widget, combo_index: int | None = None) -> bool:
    """Commit a tagged settings control without opening dropdowns or showing UI.

    Returns True if a mutation was attempted.
    """
    if widget is None:
        return False
    if combo_index is not None:
        set_index = getattr(widget, "setCurrentIndex", None)
        count = int(getattr(widget, "count", lambda: 0)())
        if callable(set_index) and 0 <= combo_index < count:
            set_index(combo_index)
            return True
        return False

    is_checkable = getattr(widget, "isCheckable", None)
    if callable(is_checkable) and is_checkable():
        if hasattr(widget, "isChecked") and hasattr(widget, "setChecked"):
            # Radios: turn this one on. Checkboxes: toggle.
            exclusive = getattr(widget, "autoExclusive", None)
            if callable(exclusive) and exclusive():
                widget.setChecked(True)
            elif getattr(widget, "group", None) is not None:
                widget.setChecked(True)
            else:
                widget.setChecked(not bool(widget.isChecked()))
            return True

    if hasattr(widget, "isChecked") and hasattr(widget, "setChecked"):
        # Toolkit CheckBox / RadioButton without isCheckable().
        widget.setChecked(not bool(widget.isChecked()) if not _looks_like_radio(widget) else True)
        return True

    click = getattr(widget, "click", None)
    if callable(click):
        click()
        return True
    clicked = getattr(widget, "clicked", None)
    if clicked is not None and hasattr(clicked, "emit"):
        clicked.emit()
        return True
    return False


def _looks_like_radio(widget) -> bool:
    name = type(widget).__name__.lower()
    return "radio" in name


def activate_member_in_dialog(dialog: QWidget, group_key: str, member_key: str) -> bool:
    """Find and activate a tagged member under ``dialog``. Does not show UI."""
    if not member_key:
        return False
    group = None
    find_group = getattr(dialog, "group_widget_for", None)
    if callable(find_group):
        group = find_group(group_key)
    roots: list[QWidget] = []
    if isinstance(group, QWidget):
        roots.append(group)
    if isinstance(dialog, QWidget):
        roots.append(dialog)
    seen: set[int] = set()
    for root in roots:
        root_id = id(root)
        if root_id in seen:
            continue
        seen.add(root_id)
        widget, combo_index = find_tagged_member(root, member_key)
        if widget is None:
            continue
        return activate_member_control(widget, combo_index)
    return False


def resolve_member_in_subtree(
    root: QWidget,
    member_key: str,
    *,
    scroll: bool = True,
) -> QWidget | None:
    """Find a tagged control under ``root`` and prepare it for reveal."""
    if not member_key:
        return None

    widget, combo_index = find_tagged_member(root, member_key)
    if widget is None:
        return None
    if combo_index is not None:
        # Scroll the field (not the overlay row) into the page viewport.
        if scroll:
            scroll_widget_into_view(widget)
        return _prepare_combo_option(widget, member_key, combo_index)
    if scroll:
        scroll_widget_into_view(widget)
    return widget


def resolve_member_widget(
    dialog: QWidget,
    group_key: str,
    member_key: str,
) -> QWidget | None:
    """Resolve a settings member for Find Action reveal/pulse."""
    group = None
    find_group = getattr(dialog, "group_widget_for", None)
    if callable(find_group):
        group = find_group(group_key)
    roots: list[QWidget] = []
    if isinstance(group, QWidget):
        roots.append(group)
    if isinstance(dialog, QWidget):
        roots.append(dialog)
    seen: set[int] = set()
    for root in roots:
        root_id = id(root)
        if root_id in seen:
            continue
        seen.add(root_id)
        widget = resolve_member_in_subtree(root, member_key)
        if widget is not None:
            return widget
    return None


# Re-export property names for callers that still import from this module.
__all__ = [
    "PROP_COMBO_OPTIONS",
    "PROP_MEMBER",
    "activate_member_control",
    "activate_member_in_dialog",
    "combo_option_map",
    "resolve_member_in_subtree",
    "resolve_member_widget",
    "scroll_widget_into_view",
]
