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
from PySide6.QtCore import QSettings
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


def _manager_for(ini_path, org, app):
    """Explicit-file injection (pattern from test_settings_schedule_persist).

    No global QSettings.setPath redirect: each manager owns an isolated INI
    file, so sibling tests sharing the process can never observe or pollute
    this file (and vice versa). Unique org/app per manager keeps even the
    pre-injection QSettings(org, app) construction isolated.
    """
    settings = QSettings(ini_path, QSettings.Format.IniFormat)
    mgr = SettingsManager(org, app)
    mgr.settings = settings
    mgr._backup_path = settings.fileName() + ".backup"
    return mgr


def test_schedule_persist_typed_load_chain(qapp, tmp_path):
    """Dialog-apply state survives debounce + fresh manager + typed load.

    ui_mode / ui_scale_factor / theme are written by the debounced snapshot,
    then a brand-new SettingsManager (simulating the next app start) loads
    them into a new Store with their declared types preserved — the raw
    INI strings must not leak through as untyped values.
    """
    ini_path = os.path.join(str(tmp_path), "persist-chain.ini")
    writer = _manager_for(ini_path, "improve-imgsli-chain-w", "chain-w")
    store = Store()
    store.settings.ui_mode = "expert"
    store.settings.ui_scale_factor = 1.5
    store.settings.theme = "dark"

    writer.schedule_persist(store)
    _settle()
    writer.settings.sync()
    # Drain any pending singleShot before the fresh manager reads, so no
    # debounced write can leak past this test into a sibling test.
    qapp.processEvents()

    fresh = _manager_for(ini_path, "improve-imgsli-chain-r", "chain-r")
    reloaded = Store()
    fresh.load_all_settings(reloaded)

    assert reloaded.settings.ui_mode == "expert"
    assert abs(reloaded.settings.ui_scale_factor - 1.5) < 1e-9
    assert reloaded.settings.theme == "dark"
    # The untouched field kept its default through the whole chain.
    assert reloaded.settings.current_language == "en"
    # No debounced write may outlive the test: the singleShot fired during
    # _settle, and the final drain guarantees it before teardown.
    qapp.processEvents()
    assert not writer._persist_pending
