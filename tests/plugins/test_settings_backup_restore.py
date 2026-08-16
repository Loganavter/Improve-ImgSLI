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