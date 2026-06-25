"""Multi Compare export plugin."""

from __future__ import annotations

from importlib import import_module

__all__ = ["MultiCompareExportDialog", "MultiCompareExportDialogState"]


def __getattr__(name: str):
    if name == "MultiCompareExportDialog":
        module = import_module("tabs.multi_compare.plugins.export.dialog")
    elif name == "MultiCompareExportDialogState":
        module = import_module("tabs.multi_compare.plugins.export.models")
    else:
        raise AttributeError(name)
    value = getattr(module, name)
    globals()[name] = value
    return value
