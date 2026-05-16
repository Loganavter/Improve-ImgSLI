from __future__ import annotations

from importlib import import_module

__all__ = [
    "Action",
    "ActionType",
    "Dispatcher",
    "ViewportReducer",
    "DocumentReducer",
    "SettingsReducer",
    "RootReducer",
]

_EXPORTS = {
    "Action": ("core.state_management.actions", "Action"),
    "ActionType": ("core.state_management.actions", "ActionType"),
    "Dispatcher": ("core.state_management.dispatcher", "Dispatcher"),
    "ViewportReducer": ("core.state_management.reducers", "ViewportReducer"),
    "DocumentReducer": ("core.state_management.reducers", "DocumentReducer"),
    "SettingsReducer": ("core.state_management.reducers", "SettingsReducer"),
    "RootReducer": ("core.state_management.reducers", "RootReducer"),
}

def __getattr__(name: str):
    target = _EXPORTS.get(name)
    if target is None:
        raise AttributeError(name)
    module_name, attr_name = target
    module = import_module(module_name)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value
