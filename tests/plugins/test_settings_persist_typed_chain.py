"""Debounced schedule_persist -> FRESH SettingsManager -> typed load chain.

``test_settings_schedule_persist.py`` pins the debounced single-writer
semantics at the raw-QSettings level, and the root full pass
(``tests/runtime/test_settings_full_pass.py``) pins save->load on the *same*
manager instance. Neither covers the full dialog-apply roundtrip: a debounced
``schedule_persist(store)`` landing on disk, then a *fresh* SettingsManager
instance (as at next app start) loading that file back into a new Store with
typed values — not just raw QSettings strings.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QSettings, QStandardPaths
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from core.store import Store
from plugins.settings.manager import SettingsManager


def _settle():
    """Advance past the 150 ms persist debounce."""
    QTest.qWait(220)


@pytest.fixture
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _redirect_qsettings(tmp_path):
    """Point org/app QSettings at an isolated ini file.

    The SettingsManager's ``QSettings(org, app)`` resolves with the Native
    format on Linux (the 2-arg constructor ignores ``setDefaultFormat``), so
    BOTH format paths must be redirected — canonical pattern from
    tests/runtime/test_settings_full_pass.py::_redirect_qsettings. Returns
    the previous format/path so the caller restores them (the redirect is
    process-global; the tests must never write to the real user config).
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


def test_schedule_persist_typed_load_chain(qapp, tmp_path):
    """Dialog-apply state survives debounce + fresh manager + typed load.

    ui_mode / ui_scale_factor / theme are written by the debounced snapshot,
    then a brand-new SettingsManager (simulating the next app start) loads
    them into a new Store with their declared types preserved — the raw
    INI strings must not leak through as untyped values.
    """
    previous_format, previous_path = _redirect_qsettings(tmp_path)
    try:
        writer = SettingsManager("improve-imgsli", "improve-imgsli")
        store = Store()
        store.settings.ui_mode = "expert"
        store.settings.ui_scale_factor = 1.5
        store.settings.theme = "dark"

        writer.schedule_persist(store)
        _settle()

        fresh = SettingsManager("improve-imgsli", "improve-imgsli")
        reloaded = Store()
        fresh.load_all_settings(reloaded)

        assert reloaded.settings.ui_mode == "expert"
        assert abs(reloaded.settings.ui_scale_factor - 1.5) < 1e-9
        assert reloaded.settings.theme == "dark"
        # The untouched field kept its default through the whole chain.
        assert reloaded.settings.current_language == "en"
    finally:
        _restore_qsettings(previous_format, previous_path)
