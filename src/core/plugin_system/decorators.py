from __future__ import annotations

from typing import Callable, Type

_REGISTERED_PLUGINS: list[Type] = []

def plugin(name: str, version: str = "1.0") -> Callable[[Type], Type]:
    def decorator(cls: Type) -> Type:
        cls._plugin_meta = {"name": name, "version": version}
        if cls not in _REGISTERED_PLUGINS:
            _REGISTERED_PLUGINS.append(cls)
        return cls

    return decorator

def get_registered_plugins() -> tuple[Type, ...]:
    return tuple(_REGISTERED_PLUGINS)

