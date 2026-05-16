from __future__ import annotations

from importlib import import_module

__all__ = [
    "BodyLabel",
    "CaptionLabel",
    "CheckBox",
    "RadioButton",
    "Slider",
    "Switch",
    "VideoSessionWidget",

    "FluentCheckBox",
    "FluentRadioButton",
    "FluentSlider",
    "FluentSwitch",
]

_SIMPLE_EXPORTS = {
    "BodyLabel": ("sli_ui_toolkit.widgets", "BodyLabel"),
    "CaptionLabel": ("sli_ui_toolkit.widgets", "CaptionLabel"),
    "CheckBox": ("sli_ui_toolkit.widgets", "CheckBox"),
    "RadioButton": ("sli_ui_toolkit.widgets", "RadioButton"),
    "Slider": ("sli_ui_toolkit.widgets", "Slider"),
    "Switch": ("sli_ui_toolkit.widgets", "Switch"),

    "FluentCheckBox": ("sli_ui_toolkit.widgets", "CheckBox"),
    "FluentRadioButton": ("sli_ui_toolkit.widgets", "RadioButton"),
    "FluentSlider": ("sli_ui_toolkit.widgets", "Slider"),
    "FluentSwitch": ("sli_ui_toolkit.widgets", "Switch"),
    "VideoSessionWidget": ("ui.widgets.video_session_widget", "VideoSessionWidget"),
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
