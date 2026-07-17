"""Resolve help hub/page icons from the app pack + tree-contributed resolvers."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from PySide6.QtGui import QIcon

from ui.icon_manager import AppIcon, get_app_icon

IconResolver = Callable[[str], QIcon | None]


def resolve_help_icon(
    name: str | None,
    *,
    resolvers: Iterable[IconResolver] | None = None,
) -> QIcon:
    if not name:
        return get_app_icon(AppIcon.HELP)
    icon = get_app_icon(name)
    if not icon.isNull():
        return icon
    for resolver in resolvers or ():
        try:
            found = resolver(name)
        except Exception:
            continue
        if found is not None and not found.isNull():
            return found
    return get_app_icon(AppIcon.HELP)
