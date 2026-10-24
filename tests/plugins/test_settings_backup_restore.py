"""Settings file health check + backup self-heal.

Regression family: QSettings writes its INI in place (open-truncate-write-
close), so a crash/kill mid-save leaves a truncated file — the next startup
would load defaults and a clean exit would re-write them, permanently wiping
the user's settings. ``_restore_backup_if_corrupt`` heals a file that exists
but is missing the critical keys from the last-good ``.backup``. The health
check itself must NOT touch a healthy file.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from pathlib import Path
from PySide6.QtCore import QSettings, QStandardPaths
from PySide6.QtWidgets import QApplication

from plugins.settings.manager import SettingsManager


def _redirect_qsettings(tmp_path):
    """Point org/app QSettings at an isolated ini file.

    ``QSettings(org, app)`` resolves with the Native format on Linux (the
    2-arg constructor ignores ``setDefaultFormat``), so BOTH format paths
    must be redirected or these tests would read/write the real user
    config at ~/.config/improve-imgsli.
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


@pytest.fixture
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def qsettings_redirect(tmp_path):
    previous_format, previous_path = _redirect_qsettings(tmp_path)
    yield
    _restore_qsettings(previous_format, previous_path)


def _settings_path(tmp_path) -> str:
    path = QSettings("improve-imgsli", "improve-imgsli").fileName()
    # Safety net: this test writes/removes files at the resolved path. If
    # the redirect ever breaks again, fail loudly instead of touching the
    # real user config at ~/.config/improve-imgsli.
    assert str(tmp_path) in path, (
        f"test would touch the real settings file: {path}"
    )
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return path


def test_restores_truncated_file_from_backup(qapp, qsettings_redirect, tmp_path):
    """A file present but missing the critical keys is healed from backup."""
    path = _settings_path(tmp_path)
    with open(path, "w") as f:
        f.write("[general]\nother_setting=1\n")
    backup = path + ".backup"
    with open(backup, "w") as f:
        f.write("[general]\ntheme=dark\nlanguage=ru\n")

    SettingsManager("improve-imgsli", "improve-imgsli")

    healed = QSettings("improve-imgsli", "improve-imgsli")
    assert healed.value("theme") == "dark"
    assert healed.value("language") == "ru"
    assert healed.value("other_setting") is None, (
        "the corrupt content must be replaced by the backup, not merged"
    )


def test_no_restore_when_file_has_critical_keys(qapp, qsettings_redirect, tmp_path):
    """A healthy file (theme present) is left untouched, backup ignored."""
    path = _settings_path(tmp_path)
    with open(path, "w") as f:
        f.write("[general]\ntheme=auto\nlanguage=en\n")
    backup = path + ".backup"
    with open(backup, "w") as f:
        f.write("[general]\ntheme=dark\nlanguage=ru\n")

    manager = SettingsManager("improve-imgsli", "improve-imgsli")

    assert manager.settings.value("theme") == "auto"
    assert manager.settings.value("language") == "en"


def test_missing_file_is_not_a_restore_trigger(qapp, qsettings_redirect, tmp_path):
    """A genuinely fresh profile (no file, no backup) must not restore
    anything — the health check is a no-op, not a crash."""
    path = _settings_path(tmp_path)
    backup = path + ".backup"
    if os.path.exists(backup):
        os.remove(backup)

    manager = SettingsManager("improve-imgsli", "improve-imgsli")

    # QSettings may have materialized an empty ini on first touch; the
    # manager must not heal it from a (nonexistent) backup and must treat
    # the profile as fresh.
    assert not manager.settings.contains("theme")
    assert not os.path.exists(backup)


# ---------------------------------------------------------------------------
# Non-file (registry) store: the Windows shape. ``QSettings.fileName()`` is
# ``HKCU\Software\improve-imgsli\improve-imgsli`` — os.path.exists is always
# False there, so before the format-aware split the backup and the self-heal
# were silently dead code on Windows. Simulated here with an in-memory store
# that reports a registry key name; the portable export/restore is real I/O.
# ---------------------------------------------------------------------------

REGISTRY_FILE_NAME = r"HKCU\Software\improve-imgsli\improve-imgsli"


class _RegistryStore:
    """Shared in-memory stand-in for a registry-backed QSettings."""

    values: dict = {}

    def __init__(self, *args, **_kwargs):
        self._org = args[0] if args else ""
        self._app = args[1] if len(args) > 1 else ""

    @classmethod
    def reset(cls) -> None:
        cls.values = {}

    def fileName(self) -> str:  # noqa: N802 - Qt API name
        return REGISTRY_FILE_NAME

    def organizationName(self) -> str:  # noqa: N802 - Qt API name
        return self._org

    def applicationName(self) -> str:  # noqa: N802 - Qt API name
        return self._app

    def allKeys(self) -> list[str]:  # noqa: N802 - Qt API name
        return list(self.values)

    def contains(self, key) -> bool:  # noqa: N802 - Qt API name
        return key in self.values

    def value(self, key, default=None):  # noqa: N802 - Qt API name
        return self.values.get(key, default)

    def setValue(self, key, value) -> None:  # noqa: N802 - Qt API name
        self.values[key] = value

    def sync(self) -> None:
        pass


class _RegistryQSettingsFactory:
    """Drop-in for the module-level ``QSettings`` name in the manager.

    Org/app construction (no explicit path) returns the in-memory registry
    store; an explicit ``(path, Format.IniFormat)`` keeps the real QSettings
    because that is the portable export file, not the live store.
    """

    Format = QSettings.Format

    def __call__(self, *args, **kwargs):
        if len(args) >= 2 and isinstance(args[1], QSettings.Format):
            return QSettings(*args, **kwargs)
        return _RegistryStore(*args, **kwargs)


class _FakeStandardPaths:
    """App-config dir pinned to a tmp dir (no dependency on the host)."""

    class StandardLocation:
        GenericConfigLocation = object()

    def __init__(self, directory):
        self._directory = str(directory)

    def writableLocation(self, _location):  # noqa: N802 - Qt API name
        return self._directory


@pytest.fixture
def registry_store(tmp_path, monkeypatch):
    """Simulated Windows registry store + a controllable app-config dir."""
    import plugins.settings.manager as manager_module

    _RegistryStore.reset()
    monkeypatch.setattr(manager_module, "QSettings", _RegistryQSettingsFactory())
    monkeypatch.setattr(
        manager_module, "QStandardPaths", _FakeStandardPaths(tmp_path / "cfg")
    )
    monkeypatch.setattr(manager_module, "_backup_warning_emitted", False)
    yield manager_module
    _RegistryStore.reset()


def _portable_backup(tmp_path) -> Path:
    return (
        tmp_path
        / "cfg"
        / "improve-imgsli"
        / "improve-imgsli"
        / "settings-backup.ini"
    )


def test_is_file_backed_settings_classifies_registry_vs_file(tmp_path):
    from plugins.settings.manager import is_file_backed_settings
    assert is_file_backed_settings(REGISTRY_FILE_NAME) is False
    assert is_file_backed_settings(
        str(tmp_path / "settings.ini")
    ) is True
    # Windows drive paths and UNC shares are files, not registry keys.
    assert is_file_backed_settings(r"C:\Users\u\AppData\settings.ini") is True
    assert is_file_backed_settings(r"\\server\share\settings.ini") is True
    assert is_file_backed_settings("") is False


def test_registry_store_refreshes_portable_backup_after_save(
    qapp, registry_store, tmp_path
):
    """A non-file store still gets a last-good copy after a successful save."""
    from core.store import Store

    manager = registry_store.SettingsManager("improve-imgsli", "improve-imgsli")
    manager.save_all_settings(Store())

    backup = _portable_backup(tmp_path)
    assert backup.exists(), "portable backup must be written for a registry store"
    exported = QSettings(str(backup), QSettings.Format.IniFormat)
    assert exported.value("language") == "en"
    assert exported.value("theme") == "auto"
    # The fake store is file-less: no ".backup" path beside a fake filename.
    assert not os.path.exists(REGISTRY_FILE_NAME + ".backup")


def test_registry_store_self_heals_from_portable_backup(
    qapp, registry_store, tmp_path
):
    """A store that lost language/theme is repopulated from the export."""
    from core.store import Store

    manager = registry_store.SettingsManager("improve-imgsli", "improve-imgsli")
    store = Store()
    store.settings.theme = "dark"
    store.settings.current_language = "ru"
    manager.save_all_settings(store)
    assert _portable_backup(tmp_path).exists()

    # Truncated registry write: other keys survived, the critical pair did not.
    _RegistryStore.values.pop("theme")
    _RegistryStore.values.pop("language")
    assert "window_width" in _RegistryStore.values

    healed = registry_store.SettingsManager("improve-imgsli", "improve-imgsli")

    # Re-read from the live store, not merely "a backup file exists".
    assert healed.settings.value("theme") == "dark"
    assert healed.settings.value("language") == "ru"


def test_corrupt_portable_backup_is_fail_open(
    qapp, registry_store, tmp_path
):
    """Garbage in the export never raises and never wipes live settings."""
    backup = _portable_backup(tmp_path)
    backup.parent.mkdir(parents=True, exist_ok=True)
    backup.write_bytes(b"\x00\xff\xfe not ini \n[broken\nkey without value =\n\xff")

    # Present but missing the critical keys -> the self-heal path is entered.
    _RegistryStore.values["window_width"] = 1440

    manager = registry_store.SettingsManager("improve-imgsli", "improve-imgsli")

    assert manager.settings.value("window_width") == 1440, (
        "a corrupt backup must not clear what the live store still holds"
    )
    assert not manager.settings.contains("theme")


def test_unavailable_backup_warns_exactly_once(
    qapp, registry_store, monkeypatch, caplog
):
    """No writable config dir => one loud warning, not silent debug."""
    import logging

    import plugins.settings.manager as manager_module

    class _NoConfigDir:
        class StandardLocation:
            GenericConfigLocation = object()

        def writableLocation(self, _location):  # noqa: N802 - Qt API name
            return ""

    monkeypatch.setattr(manager_module, "QStandardPaths", _NoConfigDir())
    caplog.set_level(logging.WARNING)

    _RegistryStore.values["window_width"] = 1280  # present, no critical keys
    manager = registry_store.SettingsManager("improve-imgsli", "improve-imgsli")
    manager._refresh_backup()
    manager._refresh_backup()

    warnings = [
        record
        for record in caplog.records
        if "Settings backup/self-heal is unavailable" in record.getMessage()
    ]
    assert len(warnings) == 1, [r.getMessage() for r in caplog.records]


def test_ini_store_keeps_backup_beside_the_file(qapp, qsettings_redirect, tmp_path):
    """The file-backed branch is unchanged: <settings.ini>.backup + restore."""
    path = _settings_path(tmp_path)
    manager = SettingsManager("improve-imgsli", "improve-imgsli")
    manager._save_setting("theme", "dark")
    manager._save_setting("language", "ru")
    manager.settings.sync()
    manager._refresh_backup()

    backup = path + ".backup"
    assert os.path.exists(backup)
    with open(path, "w") as f:  # truncate: critical keys gone
        f.write("[general]\nother_setting=1\n")

    SettingsManager("improve-imgsli", "improve-imgsli")
    healed = QSettings("improve-imgsli", "improve-imgsli")
    assert healed.value("theme") == "dark"
    assert healed.value("language") == "ru"


# ---------------------------------------------------------------------------
# One store: every settings user resolves to the canonical org/app pair.
# ---------------------------------------------------------------------------


def test_bare_qsettings_sites_use_canonical_pair(monkeypatch):
    from core.plugin_system.settings import (
        SETTINGS_APP,
        SETTINGS_ORG,
        PluginSettings,
        canonical_settings,
    )
    from ui.widgets.color.recents import RecentColorsStore

    assert (SETTINGS_ORG, SETTINGS_APP) == ("improve-imgsli", "improve-imgsli")

    calls: list[tuple] = []
    real_qsettings = QSettings

    def _recording_qsettings(*args, **kwargs):
        calls.append(args)
        return real_qsettings(*args, **kwargs)

    import core.plugin_system.settings as settings_module

    monkeypatch.setattr(settings_module, "QSettings", _recording_qsettings)

    canonical_settings()
    PluginSettings("demo")
    RecentColorsStore()

    assert calls, "the canonical factory must construct a QSettings"
    assert all(args == (SETTINGS_ORG, SETTINGS_APP) for args in calls), calls


def test_no_bare_qsettings_construction_in_canonical_users():
    """Structural guard: no zero-arg QSettings() left in the two sites."""
    import ast
    from pathlib import Path as _Path

    root = _Path(__file__).resolve().parents[2] / "src"
    for relative in (
        "core/plugin_system/settings.py",
        "ui/widgets/color/recents.py",
    ):
        tree = ast.parse((root / relative).read_text(encoding="utf-8"))
        bare = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "QSettings"
            and not node.args
            and not node.keywords
        ]
        assert not bare, f"{relative} still constructs a bare QSettings()"
