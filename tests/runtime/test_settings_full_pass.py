"""Settings persistence full pass — one sweep over the entire surface.

Replaces the per-setting "individual" persistence tests: instead of a hand-
written test per value, this suite derives the whole settings surface from
the same AST scanners the contract uses (tests/contracts/_framework.py —
see docs/dev/CONTRACTS.md §Settings persistence contract) and verifies the
behavioral half of the contract:

1. **Fixpoint sweep** — for every (scope, field, key, type) loaded by
   ``SettingsManager.load_all_settings``: put a non-default value into the
   store, run ``save_all_settings``, reload into a fresh store, and assert
   the value survives. A drift here means the declared type does not match
   the actual roundtrip format (the contract only guarantees the type is
   *declared*; this test guarantees it is *true*).
2. **Out-of-band blob** — ``keyboard_overrides`` (JSON) roundtrips.
3. **Startup application** — the persisted store values reach the process-
   wide singletons (UiScale) during bootstrap, before any UI is built.

Canvas-feature properties (divider thickness, guides, …) are swept in the
tab-owned suite: ``src/tabs/image_compare/tests/plugins/`` (root tests must
not import tab internals — tests/contracts/test_root_tests_no_tab_internals_leak.py).
"""

from __future__ import annotations

import ast

import pytest
from PySide6.QtCore import QSettings, QStandardPaths

from core.store import Store
from domain.types import Color
from plugins.settings.manager import SettingsManager
from tests.contracts._framework import (
    MANAGER_PATH,
    read,
    settings_load_pairs,
)

_TREE = ast.parse(read(MANAGER_PATH))

#: scope name (from load_all_settings) -> store accessor path.
_SCOPE_ACCESSORS = {
    "s": ("settings",),
    "render": ("viewport", "render_config"),
    "view": ("viewport", "view_state"),
}

_COLOR_FIELDS = {
    "export_background_color",
    "file_name_color",
    "file_name_bg_color",
}

#: Fields whose semantic range is narrower than their declared type (the
#: load path clamps). The sweep must use an in-range value or the clamp
#: would report a false drift. Keep in sync with the UI control ranges.
_RANGE_SAFE_VALUES = {
    "text_alpha_percent": 55,  # font flyout opacity slider: 5..100
}


def _obj(store: Store, scope: str):
    obj = store
    for attr in _SCOPE_ACCESSORS[scope]:
        obj = getattr(obj, attr)
    return obj


def _non_default(store: Store, scope: str, field: str, type_name: str):
    current = getattr(_obj(store, scope), field)
    if field in _COLOR_FIELDS:
        return Color(11, 22, 33, 200)
    if field in _RANGE_SAFE_VALUES:
        return _RANGE_SAFE_VALUES[field]
    if type_name == "bool":
        return not bool(current)
    if type_name == "int":
        return int(current) + 1
    if type_name == "float":
        return float(current) + 1.5
    return f"{current}-pass"


def _equal(a, b) -> bool:
    if isinstance(a, Color) and isinstance(b, Color):
        return (a.r, a.g, a.b, a.a) == (b.r, b.g, b.b, b.a)
    if isinstance(a, float) or isinstance(b, float):
        return abs(float(a) - float(b)) < 1e-9
    return a == b


def _redirect_qsettings(tmp_path):
    """Point org/app QSettings at an isolated ini file.

    The SettingsManager's ``QSettings(org, app)`` resolves with the
    *Native* format on Linux (the 2-arg constructor ignores
    ``setDefaultFormat``), so BOTH format paths must be redirected —
    otherwise every full-pass save writes a fresh-Store snapshot straight
    into the real user config at ~/.config/improve-imgsli (observed: user
    settings silently reset to defaults + ui_scale 1.5 between app runs).

    Returns the previous format/path so the caller restores them (the
    redirect is process-global; the tests must never write to the real
    user config).
    """
    previous_format = QSettings.defaultFormat()
    previous_path = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.ConfigLocation
    )
    QSettings.setPath(
        QSettings.Format.NativeFormat, QSettings.Scope.UserScope, str(tmp_path)
    )
    QSettings.setPath(
        QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path)
    )
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    return previous_format, previous_path


def _restore_qsettings(previous_format, previous_path) -> None:
    QSettings.setDefaultFormat(previous_format)
    QSettings.setPath(
        QSettings.Format.NativeFormat, QSettings.Scope.UserScope, previous_path
    )
    QSettings.setPath(
        QSettings.Format.IniFormat, QSettings.Scope.UserScope, previous_path
    )


def test_qsettings_redirect_isolates_manager(tmp_path):
    """The org/app QSettings must resolve under tmp_path, never the real
    config — a broken redirect silently wipes the user's settings.

    Regression: the redirect used to set only the IniFormat path while
    ``SettingsManager``'s ``QSettings(org, app)`` resolves with the Native
    format, so the full-pass saves landed in ~/.config/improve-imgsli.
    """
    previous_format, previous_path = _redirect_qsettings(tmp_path)
    try:
        manager = SettingsManager("improve-imgsli", "improve-imgsli")
        path = manager.settings.fileName()
        assert str(tmp_path) in path, (
            f"org/app QSettings must land under the isolated tmp dir, got {path}"
        )
    finally:
        _restore_qsettings(previous_format, previous_path)


def test_settings_manager_full_pass_roundtrip(qapp, tmp_path, monkeypatch):
    """Every typed setting survives save_all_settings -> load_all_settings."""
    pairs = settings_load_pairs(_TREE)
    assert pairs, "settings surface must not be empty"

    previous_format, previous_path = _redirect_qsettings(tmp_path)
    try:
        manager = SettingsManager("improve-imgsli", "improve-imgsli")
        failures = []
        for pair in pairs:
            scope, field, key, type_name = (
                pair["scope"],
                pair["field"],
                pair["key"],
                pair["type"],
            )
            store = Store()
            value = _non_default(store, scope, field, type_name)
            setattr(_obj(store, scope), field, value)
            manager.save_all_settings(store)

            reloaded = Store()
            manager.load_all_settings(reloaded)
            got = getattr(_obj(reloaded, scope), field)
            if not _equal(got, value):
                failures.append(
                    f"{scope}.{field} ({key!r}, {type_name}): saved {value!r}, "
                    f"came back {got!r}"
                )
        assert not failures, (
            "settings that drift across save->load: the declared type does "
            "not match the real roundtrip format:\n  - " + "\n  - ".join(failures)
        )
    finally:
        _restore_qsettings(previous_format, previous_path)


def test_keyboard_overrides_json_full_pass(qapp, tmp_path, monkeypatch):
    """The JSON blob (keyboard_overrides) survives the full pass."""
    previous_format, previous_path = _redirect_qsettings(tmp_path)
    try:
        manager = SettingsManager("improve-imgsli", "improve-imgsli")
        store = Store()
        store.settings.keyboard_overrides = {"ctrl+o": "open", "f1": ""}
        manager.save_all_settings(store)

        reloaded = Store()
        manager.load_all_settings(reloaded)
        assert reloaded.settings.keyboard_overrides == {
            "ctrl+o": "open",
            "f1": "",
        }
    finally:
        _restore_qsettings(previous_format, previous_path)


def test_bootstrap_applies_persisted_settings_before_ui(qapp, tmp_path, monkeypatch):
    """Startup reaches the process-wide singletons with the persisted values.

    Generic form of the old per-setting regression: whatever
    ``load_all_settings`` put into the store must be applied to the shared
    chrome managers (UiScale) during ``ApplicationContext._load_persistent_state``
    — otherwise the interface renders at defaults while the store (and the
    settings dialog) still shows the saved values.
    """
    from sli_ui_toolkit.managers import UiScale

    previous_factor = UiScale.get_instance().factor()
    previous_format, previous_path = _redirect_qsettings(tmp_path)
    try:
        seed = SettingsManager("improve-imgsli", "improve-imgsli")
        seed._save_setting("ui_scale_factor", 1.5)

        from core.bootstrap import ApplicationContext

        ctx = ApplicationContext()
        ctx._build_core_services()
        ctx._load_persistent_state()

        assert abs(ctx.store.settings.ui_scale_factor - 1.5) < 1e-9
        assert abs(UiScale.get_instance().factor() - 1.5) < 1e-9
    finally:
        _restore_qsettings(previous_format, previous_path)
        UiScale.get_instance().set_factor(previous_factor)