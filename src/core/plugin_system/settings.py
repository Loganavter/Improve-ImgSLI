from __future__ import annotations

from dataclasses import fields, is_dataclass
from enum import Enum
from typing import Any

from PyQt6.QtCore import QSettings

class SettingsScope(Enum):
    GLOBAL = "global"
    PLUGIN = "plugin"

class PluginSettings:
    def __init__(self, plugin_name: str, scope: SettingsScope = SettingsScope.PLUGIN):
        self.plugin_name = plugin_name
        self.scope = scope
        self._settings = QSettings()

    def _build_key(self, key: str) -> str:
        return f"{self.scope.value}/{self.plugin_name}/{key}"

    def get_value(self, key: str, default: Any = None) -> Any:
        return self._settings.value(self._build_key(key), default)

    def set_value(self, key: str, value: Any) -> None:
        if value is None:
            return
        self._settings.setValue(self._build_key(key), value)

    def load_dataclass(self, instance: Any) -> Any:
        if not is_dataclass(instance):
            return instance

        for field in fields(instance):
            existing = getattr(instance, field.name, None)
            stored = self._settings.value(self._build_key(field.name), None)
            if stored is not None:
                try:
                    setattr(instance, field.name, stored)
                except Exception:
                    setattr(instance, field.name, existing)

        return instance

    def persist_dataclass(self, instance: Any) -> None:
        if not is_dataclass(instance):
            return

        for field in fields(instance):
            value = getattr(instance, field.name, None)
            self.set_value(field.name, value)

def auto_persist(cls: type) -> type:
    setattr(cls, "_auto_persist", True)
    return cls

