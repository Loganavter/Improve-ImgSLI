from __future__ import annotations

from importlib import import_module

__all__ = [
    "Label",
    "CheckBox",
    "RadioButton",
    "Slider",
    "Switch",
]

_SIMPLE_EXPORTS = {
    "Label": ("sli_ui_toolkit.widgets", "Label"),
    "CheckBox": ("sli_ui_toolkit.widgets", "CheckBox"),
    "RadioButton": ("sli_ui_toolkit.widgets", "RadioButton"),
    "Slider": ("sli_ui_toolkit.widgets", "Slider"),
    "Switch": ("sli_ui_toolkit.widgets", "Switch"),
}


def __getattr__(name: str):
    target = _SIMPLE_EXPORTS.get(name)
    if target is None:
        raise AttributeError(name)
    module_name, attr_name = target
    module = import_module(module_name)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value
