from __future__ import annotations

from importlib import import_module

__all__ = ["VideoEditorPlugin"]

def __getattr__(name: str):
    if name != "VideoEditorPlugin":
        raise AttributeError(name)
    module = import_module("tabs.image_compare.video_editor.plugin")
    value = getattr(module, name)
    globals()[name] = value
    return value
