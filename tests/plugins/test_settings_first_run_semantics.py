"""First run means "empty profile", not "the is_first_run key is missing".

Regression family: ``is_first_run`` used to treat an ABSENT ``is_first_run``
key as a fresh install. Nothing ever removes the key, but a ``.backup``
restore, a partial conf restore, or an upgrade from a version that predates
the key all produce a long-used profile without it — and the onboarding
overlay silently re-armed on the next onboarding-capable tab. The rule is
now: an absent key is first run only when the settings file carries nothing
but startup bookkeeping. These tests pin the four cases (used-without-flag,
genuinely fresh, explicitly completed, restored backup/partial conf) plus
the cache-purge-notice discriminator that reads the same pair of facts.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QSettings, QStandardPaths
from PySide6.QtWidgets import QApplication

from plugins.settings.manager import SettingsManager

ORG = "improve-imgsli"
APP = "improve-imgsli"


def _redirect_qsettings(tmp_path):
    """Point org/app QSettings at an isolated ini file.

    ``QSettings(org, app)`` resolves with the Native format on Linux (the
    2-arg constructor ignores ``setDefaultFormat``), so BOTH format paths
    must be redirected or these tests would read/write the real user config.
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
    path = QSettings(ORG, APP).fileName()
    # Safety net: this test writes files at the resolved path. If the
    # redirect ever breaks, fail loudly instead of touching the real config.
    assert str(tmp_path) in path, f"test would touch the real settings file: {path}"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return path


def _write_ini(path: str, body: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write("[general]\n" + body)


def test_user_settings_without_flag_is_not_first_run(
    qapp, qsettings_redirect, tmp_path
):
    """A used profile whose is_first_run key was lost must not re-arm."""
    path = _settings_path(tmp_path)
    _write_ini(path, "theme=dark\nlanguage=ru\nui_mode=advanced\n")

    manager = SettingsManager(ORG, APP)

    assert manager.is_first_run() is False


def test_fresh_profile_is_first_run_even_after_startup_bookkeeping(
    qapp, qsettings_redirect, tmp_path
):
    """A brand-new config has no keys; bootstrap's own version write must
    not be mistaken for user state (it happens on EVERY start, including
    the first one, before onboarding can be shown)."""
    manager = SettingsManager(ORG, APP)
    assert manager.is_first_run() is True

    manager.set_last_seen_app_version("9.9.9")
    manager.settings.sync()

    assert manager.is_first_run() is True


def test_explicitly_completed_profile_is_never_first_run(
    qapp, qsettings_redirect, tmp_path
):
    """The explicit completion marker still wins over everything."""
    path = _settings_path(tmp_path)
    _write_ini(path, "is_first_run=false\n")

    manager = SettingsManager(ORG, APP)

    assert manager.is_first_run() is False


def test_restored_backup_counts_as_past_first_run(
    qapp, qsettings_redirect, tmp_path
):
    """The observed failure: corrupt/truncated file healed from a .backup
    that predates (or lost) the is_first_run key."""
    path = _settings_path(tmp_path)
    _write_ini(path, "window_width=0\n")  # truncated: no theme/language
    _write_ini(path + ".backup", "theme=light\nlanguage=en\nui_scale_factor=1.25\n")

    manager = SettingsManager(ORG, APP)

    assert manager.settings.value("theme") == "light"
    assert manager.is_first_run() is False


def test_partial_conf_restore_counts_as_past_first_run(
    qapp, qsettings_redirect, tmp_path
):
    """A partial restore (even a single surviving user setting) is past first run."""
    path = _settings_path(tmp_path)
    _write_ini(path, "export_last_format=PNG\n")

    manager = SettingsManager(ORG, APP)

    assert manager.is_first_run() is False


def test_cache_purge_discriminator_separates_fresh_from_restored(
    qapp, qsettings_redirect, tmp_path
):
    """``_maybe_flag_cache_purge_notice`` keys off
    ``not is_first_run() and not last_seen_app_version()``:
    - fresh install -> first run True, version "" -> no notice;
    - restored old profile -> first run False, version "" -> notice.
    The new rule must keep both sides intact."""
    fresh = SettingsManager(ORG, APP)
    assert fresh.is_first_run() is True
    assert fresh.last_seen_app_version() == ""

    path = _settings_path(tmp_path)
    _write_ini(path, "theme=dark\nlanguage=ru\n")
    restored = SettingsManager(ORG, APP)
    assert restored.is_first_run() is False
    assert restored.last_seen_app_version() == ""
