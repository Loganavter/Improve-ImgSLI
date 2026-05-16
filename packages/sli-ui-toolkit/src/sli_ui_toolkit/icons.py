from collections.abc import Callable
from typing import Any

from PyQt6.QtGui import QIcon

from sli_ui_toolkit.ui.services.icon_service import (
    IconService,
    get_icon_by_name,
    get_icon_service,
)
from sli_ui_toolkit.ui.managers.icon_manager import get_icon_by_path, get_themed_icon

_icon_resolver: Callable[[Any], QIcon] | None = None
_named_icons: dict[str, Any] = {}

def configure_icon_resolver(
    resolver: Callable[[Any], QIcon] | None,
    *,
    named_icons: dict[str, Any] | None = None,
) -> None:
    global _icon_resolver, _named_icons
    _icon_resolver = resolver
    _named_icons = dict(named_icons or {})

def resolve_icon(icon: Any) -> QIcon:
    if icon is None:
        return QIcon()
    if isinstance(icon, QIcon):
        return icon
    if isinstance(icon, str):
        mapped = _named_icons.get(icon)
        if mapped is not None:
            if _icon_resolver is not None:
                return _icon_resolver(mapped)
            return get_icon_by_name(getattr(mapped, "value", mapped))
        return get_icon_by_name(icon)
    if _icon_resolver is not None:
        return _icon_resolver(icon)
    value = getattr(icon, "value", None)
    if isinstance(value, str):
        return get_icon_by_name(value)
    return QIcon()

def get_named_icon(name: str) -> Any:
    return _named_icons.get(name)

__all__ = [
    "IconService",
    "configure_icon_resolver",
    "get_icon_by_name",
    "get_icon_by_path",
    "get_icon_service",
    "get_named_icon",
    "get_themed_icon",
    "resolve_icon",
]
