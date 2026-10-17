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


def test_load_and_apply_applies_store_geometry(qtbot, tmp_path, monkeypatch):
    """Startup with a store: the persisted rect is applied to the window."""
    store = Store()
    store.settings.window_x = _X
    store.settings.window_y = _Y
    store.settings.window_width = _W
    store.settings.window_height = _H
    store.settings.window_was_maximized = False
    manager = _make_manager(qtbot, _settings(tmp_path), store=store)
    # Roomy screen: this test is about persistence, not the screen fit.
    monkeypatch.setattr(manager, "_available_rect", lambda: (0, 0, 1920, 1080))

    manager.load_and_apply()

    assert (manager.window.x(), manager.window.y()) == (_X, _Y)
    assert (manager.window.width(), manager.window.height()) == (_W, _H)
    assert not manager.window.isMaximized()


def test_load_and_apply_restores_qsettings_normal_rect_when_storeless(qtbot, tmp_path, monkeypatch):
    """Store-less startup: the saved normal_rect (not the raw geometry
    QByteArray) is what the window geometry is restored from."""
    settings = _settings(tmp_path)
    settings.setValue("normal_rect", f"{_X},{_Y},{_W},{_H}")
    manager = _make_manager(qtbot, settings, store=None)
    monkeypatch.setattr(manager, "_available_rect", lambda: (0, 0, 1920, 1080))

    manager.load_and_apply()

    assert (manager.window.x(), manager.window.y()) == (_X, _Y)
    assert (manager.window.width(), manager.window.height()) == (_W, _H)


def test_load_and_apply_defaults_to_1024x768_when_nothing_saved(qtbot, tmp_path, monkeypatch):
    """First run with nothing persisted falls back to the 1024x768 default
    and records it as the normal geometry."""
    manager = _make_manager(qtbot, _settings(tmp_path), store=None)
    monkeypatch.setattr(manager, "_available_rect", lambda: (0, 0, 1920, 1080))

    manager.load_and_apply()

    assert manager.window.width() == _DEFAULT_W
    assert manager.window.height() == _DEFAULT_H
    assert manager.normal_geometry is not None and not manager.normal_geometry.isNull()


# -- screen fitting ---------------------------------------------------------


def test_fit_into_clamps_oversized_geometry_and_pulls_it_inside():
    """A size saved on a bigger display must not exceed a smaller one.

    Falsification: before this, the restored 2090x1381 rect was applied as-is
    on a 1600x1000 display; the window's off-screen part has no pixels, so a
    capture of it is part black exactly where the chrome hangs off the edge.
    """
    from utils.geometry import fit_into

    screen = (0, 0, 1600, 1000)
    assert fit_into((1080, 238, 2090, 1381), screen) == (0, 0, 1600, 1000)
    # A fitting size keeps its size but is pulled fully inside.
    assert fit_into((1500, 900, 800, 600), screen) == (800, 400, 800, 600)
    # Nothing to fit against -> untouched.
    assert fit_into((10, 20, 3000, 2000), None) == (10, 20, 3000, 2000)


def test_load_and_apply_clamps_a_restored_rect_to_the_screen(qtbot, tmp_path, monkeypatch):
    """The restored store rect goes through the screen fit, not around it."""
    settings = _settings(tmp_path)
    store = Store()
    store.set_dispatcher(Dispatcher(store))
    store.settings.window_width = 2090
    store.settings.window_height = 1381
    store.settings.window_x = 1080
    store.settings.window_y = 238
    manager = _make_manager(qtbot, settings, store=store)
    monkeypatch.setattr(manager, "_available_rect", lambda: (0, 0, 1600, 1000))

    manager.load_and_apply()

    rect = manager.window.geometry()
    assert (rect.width(), rect.height()) == (1600, 1000)
    assert (rect.x(), rect.y()) == (0, 0)
    assert manager.normal_rect_str == "0,0,1600,1000"


def test_load_and_apply_clamps_a_restored_qsettings_rect(qtbot, tmp_path, monkeypatch):
    settings = _settings(tmp_path)
    settings.setValue("normal_rect", "900,700,2400,1400")
    settings.sync()
    manager = _make_manager(qtbot, settings)
    monkeypatch.setattr(manager, "_available_rect", lambda: (0, 0, 1600, 1000))

    manager.load_and_apply()

    rect = manager.window.geometry()
    assert (rect.width(), rect.height()) == (1600, 1000)
    assert (rect.x(), rect.y()) == (0, 0)
