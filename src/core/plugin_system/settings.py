from __future__ import annotations

from dataclasses import fields, is_dataclass
from enum import Enum
from typing import Any

from PySide6.QtCore import QSettings

from core.settings_migration import (
    LEGACY_SETTINGS_APP,
    LEGACY_SETTINGS_ORG,
    migrate_settings_once,
)

# The ONE org/app pair the whole app persists under (``SettingsManager`` is
# constructed with exactly these names from ``core.bootstrap`` and
# ``__main__``). Hand-rolled ``QSettings()`` call sites silently created a
# SECOND store ("Improve ImgSLI" defaults) that the settings manager never
# read or backed up — always resolve through ``canonical_settings``.
SETTINGS_ORG = "BlinkTable"
SETTINGS_APP = "BlinkTable"

# The pre-rename identity. Users upgrade in place, so the one-way copy in
# ``core.settings_migration`` must run before the first read of the pair
# above — re-exported here (single home for the literals) so a caller never
# spells them out again.


def canonical_settings() -> QSettings:
    """Return the app's single QSettings store (canonical org/app pair).

    Runs the one-way legacy migration first: every read of the new namespace
    goes through this factory (or ``SettingsManager``), so no code path can
    observe an empty new store while the old one still holds the user's
    settings. The migration is cached per process — this is a dict check.
    """
    migrate_settings_once()
    return QSettings(SETTINGS_ORG, SETTINGS_APP)


class SettingsScope(Enum):
    GLOBAL = "global"
    PLUGIN = "plugin"

class PluginSettings:
    def __init__(self, plugin_name: str, scope: SettingsScope = SettingsScope.PLUGIN):
        self.plugin_name = plugin_name
        self.scope = scope
        self._settings = canonical_settings()

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
            if stored is None:
                continue
            try:
                setattr(instance, field.name, _coerce_value(stored, field.type))
            except Exception:
                setattr(instance, field.name, existing)

        return instance

def auto_persist(cls: type) -> type:
    setattr(cls, "_auto_persist", True)
    return cls

_TRUE_TOKENS = frozenset({"1", "true", "yes", "on"})
_FALSE_TOKENS = frozenset({"0", "false", "no", "off", ""})


def _coerce_value(stored: Any, field_type: Any) -> Any:
    """Coerce a raw QSettings value to a dataclass field's type.

    QSettings round-trips through INI/plist as strings, so a stored
    ``"false"`` must not land in a ``bool`` field as truthy, nor ``"3"``
    in an ``int`` field as ``str``. Unknown/unsupported types pass
    through; unparseable values raise so the caller keeps the default
    (fail-open at the call site).
    """
    if isinstance(stored, field_type) if isinstance(field_type, type) else False:
        return stored
    if field_type is bool:
        if isinstance(stored, str):
            token = stored.strip().lower()
            if token in _TRUE_TOKENS:
                return True
            if token in _FALSE_TOKENS:
                return False
            raise ValueError(f"cannot coerce {stored!r} to bool")
        return bool(stored)
    if field_type is int:
        if isinstance(stored, str):
            text = stored.strip()
            try:
                return int(text)
            except ValueError:
                return int(float(text))
        return int(stored)
    if field_type is float:
        return float(stored)
    if field_type is str:
        return stored if isinstance(stored, str) else str(stored)
    return stored
