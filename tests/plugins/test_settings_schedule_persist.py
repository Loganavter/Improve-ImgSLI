"""SettingsManager.schedule_persist — the single full-snapshot writer.

Regression: the settings dialog apply path used to write individual keys
immediately, letting a stale dialog widget silently overwrite good values
with its defaults (observed "random settings reset"). The file is now only
written as a full snapshot of the Store, debounced — this test pins that
semantics: store mutations reach the file as a whole, one tick later, and
repeated schedules coalesce.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from plugins.settings.manager import SettingsManager
from core.store import Store


def _settle():
    """Advance past the 150 ms persist debounce."""
    QTest.qWait(220)


@pytest.fixture
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def manager(tmp_path):
    settings = QSettings(
        os.path.join(str(tmp_path), "cfg.ini"), QSettings.Format.IniFormat
    )
    mgr = SettingsManager("test-org", "test-app")
    mgr.settings = settings
    mgr._backup_path = settings.fileName() + ".backup"
    return mgr


def test_schedule_persist_writes_full_snapshot_later(qapp, manager):
    store = Store()
    store.settings.ui_mode = "expert"
    store.settings.ui_scale_factor = 1.5

    manager.schedule_persist(store)
    # Not yet persisted: the debounce window is open.
    assert not manager.settings.contains("ui_mode")

    # After the debounce the whole store snapshot is on disk.
    _settle()
    assert manager.settings.value("ui_mode") == "expert"
    assert float(manager.settings.value("ui_scale_factor")) == 1.5
    assert manager.settings.value("theme") == "auto"  # untouched fields too


def test_schedule_persist_coalesces(qapp, manager):
    store = Store()
    store.settings.ui_mode = "expert"
    manager.schedule_persist(store)
    store.settings.ui_mode = "advanced"
    manager.schedule_persist(store)
    _settle()
    assert manager.settings.value("ui_mode") == "advanced"


def test_schedule_persist_reusable_after_fire(qapp, manager):
    store = Store()
    store.settings.ui_mode = "expert"
    manager.schedule_persist(store)
    _settle()
    assert manager.settings.value("ui_mode") == "expert"

    store.settings.ui_mode = "advanced"
    manager.schedule_persist(store)
    _settle()
    assert manager.settings.value("ui_mode") == "advanced"