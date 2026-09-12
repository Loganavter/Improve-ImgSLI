"""GeometryManager save_on_close / load_and_apply persistence contract.

``save_on_close`` must record the window's normal (non-maximized) rect into
the Store via ``SetWindowGeometryAction`` / ``SetWindowWasMaximizedAction``
(dispatcher -> SettingsReducer -> store), and always write the QSettings
fallback keys (``normal_rect`` / ``normal_geometry`` / ``window_was_maximized``)
even without a store. ``load_and_apply`` must re-apply that geometry, and
fall back to the 1024x768 default when nothing was ever saved.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QByteArray, QSettings
from PySide6.QtWidgets import QWidget

from core.state_management.dispatcher import Dispatcher
from core.store import Store
from utils.geometry import GeometryManager

_X, _Y, _W, _H = 40, 30, 900, 640
_DEFAULT_W, _DEFAULT_H = 1024, 768


def _settings(tmp_path) -> QSettings:
    # Explicit-file QSettings: never the org/app 2-arg constructor, so no
    # redirect fixture is needed.
    return QSettings(
        os.path.join(str(tmp_path), "geometry.ini"), QSettings.Format.IniFormat
    )


def _make_manager(qtbot, settings, store=None) -> GeometryManager:
    window = QWidget()
    qtbot.addWidget(window)
    return GeometryManager(window, settings, store=store)


def test_save_on_close_records_normal_rect_into_store(qtbot, tmp_path):
    """Non-maximized close: the normal rect reaches the Store through the
    dispatcher (SetWindowGeometryAction + SetWindowWasMaximizedAction), and
    the QSettings fallback keys are written too."""
    store = Store()
    store.set_dispatcher(Dispatcher(store))
    manager = _make_manager(qtbot, _settings(tmp_path), store=store)
    manager.window.setGeometry(_X, _Y, _W, _H)
    manager.update_normal_geometry_if_needed()

    manager.save_on_close()

    assert store.settings.window_x == _X
    assert store.settings.window_y == _Y
    assert store.settings.window_width == _W
    assert store.settings.window_height == _H
    assert store.settings.window_was_maximized is False
    assert manager.settings.value("normal_rect") == f"{_X},{_Y},{_W},{_H}"
    assert manager.settings.value("window_was_maximized", False, bool) is False
    assert not manager.settings.value("normal_geometry", QByteArray(), QByteArray).isNull()


def test_save_on_close_writes_qsettings_fallback_keys_when_storeless(qtbot, tmp_path):
    """Without a store the rect still lands in QSettings under the fallback
    keys (the keys a store-less startup restores from)."""
    manager = _make_manager(qtbot, _settings(tmp_path), store=None)
    manager.window.setGeometry(_X, _Y, _W, _H)
    manager.update_normal_geometry_if_needed()

    manager.save_on_close()

    assert manager.settings.value("normal_rect") == f"{_X},{_Y},{_W},{_H}"
    assert manager.settings.value("window_was_maximized", False, bool) is False
    assert not manager.settings.value("normal_geometry", QByteArray(), QByteArray).isNull()


def test_load_and_apply_applies_store_geometry(qtbot, tmp_path):
    """Startup with a store: the persisted rect is applied to the window."""
    store = Store()
    store.settings.window_x = _X
    store.settings.window_y = _Y
    store.settings.window_width = _W
    store.settings.window_height = _H
    store.settings.window_was_maximized = False
    manager = _make_manager(qtbot, _settings(tmp_path), store=store)

    manager.load_and_apply()

    assert (manager.window.x(), manager.window.y()) == (_X, _Y)
    assert (manager.window.width(), manager.window.height()) == (_W, _H)
    assert not manager.window.isMaximized()


def test_load_and_apply_restores_qsettings_normal_rect_when_storeless(qtbot, tmp_path):
    """Store-less startup: the saved normal_rect (not the raw geometry
    QByteArray) is what the window geometry is restored from."""
    settings = _settings(tmp_path)
    settings.setValue("normal_rect", f"{_X},{_Y},{_W},{_H}")
    manager = _make_manager(qtbot, settings, store=None)

    manager.load_and_apply()

    assert (manager.window.x(), manager.window.y()) == (_X, _Y)
    assert (manager.window.width(), manager.window.height()) == (_W, _H)


def test_load_and_apply_defaults_to_1024x768_when_nothing_saved(qtbot, tmp_path):
    """First run with nothing persisted falls back to the 1024x768 default
    and records it as the normal geometry."""
    manager = _make_manager(qtbot, _settings(tmp_path), store=None)

    manager.load_and_apply()

    assert manager.window.width() == _DEFAULT_W
    assert manager.window.height() == _DEFAULT_H
    assert manager.normal_geometry is not None and not manager.normal_geometry.isNull()
