"""Shared pytest configuration for tab-owned test suites.

Every ``src/tabs/<tab>/tests/`` package needs ``src/`` on ``sys.path`` so its
tests can import ``tabs.<tab>...`` the same way ``tests/conftest.py`` does
for the top-level suite. Without this, running a single tab's tests in
isolation (``pytest src/tabs/image_compare/tests``) fails with
``ModuleNotFoundError: No module named 'tabs'`` — pytest's own rootdir
package-insertion adds the repo root (because ``src/__init__.py`` exists),
not ``src/``, and that only gets patched by accident when ``tests/conftest.py``
happens to run first in the same session.
"""

from __future__ import annotations

import os
import sys

_SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))

if _SRC not in sys.path:
    sys.path.insert(0, _SRC)


import pytest


@pytest.fixture(scope="session")
def _hermetic_tps_spill_dir(tmp_path_factory) -> str:
    """One session-scoped tmp dir for all TiledPixelStore spill memmaps."""
    return str(tmp_path_factory.mktemp("pixel_tile_store"))


@pytest.fixture(autouse=True)
def _redirect_tps_spill_to_tmp(_hermetic_tps_spill_dir, monkeypatch):
    """Keep TiledPixelStore spill files out of the real user cache.

    ``TiledPixelStore.from_pil/from_path/allocate`` (and
    ``PyramidPixelStore.build_from``) default to
    ``resolve_pixel_spill_dir()`` = ``QStandardPaths.CacheLocation`` when no
    ``tmp_dir`` is passed — in a plain test run that is the user's real
    ``~/.cache/<app>/pixel_tile_store``. Redirect the process-wide spill-dir
    cache to the session tmp dir; tests passing their own ``tmp_dir`` are
    unaffected (``tmp_dir`` wins in ``_spill_dir``).
    """
    from engine.store import tiled_pixel_store as _tps

    monkeypatch.setattr(_tps, "_spill_dir_cache", _hermetic_tps_spill_dir)


@pytest.fixture(autouse=True)
def _reset_translation_language():
    """Global current language is process-wide; isolate every test from it.

    Some tab tests switch the live language (``emit_language_changed("ru")``)
    without restoring it, which leaks into later tests whose
    ``tr(...)``-fallback assertions assume English (multi-compare footer
    tooltip containing "grid", color-picker OK == "OK"). Force English both
    before and after every test. Mirrors the same fixture in
    ``tests/conftest.py`` (tab suites run under this conftest, not that one).
    """
    import resources.translations as _translations

    _manager = _translations._manager
    _manager._current_lang = "en"
    _manager._translations = _manager.ensure_loaded("en")
    try:
        yield
    finally:
        _manager._current_lang = "en"
        _manager._translations = _manager.ensure_loaded("en")


@pytest.fixture(autouse=True)
def _reset_toolkit_config():
    """``configure_toolkit`` state is process-wide; isolate every tab test.

    Mirrors ``tests/conftest.py``: a tab test that imports ``ui.icon_manager``
    (module scope) installs the app flyout defaults and leaks them into every
    later test in the same process. Reset around each test.
    """
    from sli_ui_toolkit.config import reset_toolkit_config

    reset_toolkit_config()
    yield
    reset_toolkit_config()


@pytest.fixture(autouse=True)
def _reset_theme_manager():
    """``ThemeManager`` is a process-wide singleton; isolate every tab test.

    Without this, a tab test that flips the theme and does not restore it
    (e.g. image_compare video ``test_editor_toggle_buttons`` -> ``set_theme``)
    leaks DARK into the next tab suite, whose light-theme pixel/ink assertions
    then fail. Mirrors the same fixture in ``tests/conftest.py`` (tab suites
    run under THIS conftest, not that one). Snapshots/restores the singleton's
    mutable palette + QSS state and clears the app stylesheet.
    """
    from PySide6.QtWidgets import QApplication

    from sli_ui_toolkit.managers import ThemeManager

    tm = ThemeManager.get_instance()
    saved = (
        tm._current_theme,
        tm._light_palette,
        tm._dark_palette,
        tm._qss_template,
        list(tm._qss_paths),
    )
    try:
        yield
    finally:
        (tm._current_theme, tm._light_palette, tm._dark_palette,
         tm._qss_template, qss_paths) = saved
        tm._qss_paths = qss_paths
        app = QApplication.instance()
        if isinstance(app, QApplication) and app.styleSheet():
            app.setStyleSheet("")


@pytest.fixture(autouse=True)
def _reset_navigation_manager():
    """``NavigationManager`` (toolkit singleton) isolation for tab tests.

    A leaked test instance keeps an active section that swallows arrow keys, so
    a later tab test's ``Key_Down`` never reaches the widget handler. Mirrors the
    same fixture in ``tests/conftest.py``.
    """
    from sli_ui_toolkit.managers import NavigationManager

    def _clear() -> None:
        mgr = NavigationManager._instance
        if mgr is not None:
            try:
                mgr._uninstall_event_filter()
            except Exception:
                pass
        NavigationManager._instance = None

    _clear()
    try:
        yield
    finally:
        _clear()


@pytest.fixture(autouse=True)
def _destroy_lingering_toplevels():
    """Destroy lingering top-levels at teardown (mirrors ``tests/conftest.py``).

    Keeps stale receivers from surviving into the next test — the
    ``pytestqt:_process_events`` segfault class under ``-n``.
    """
    from PySide6.QtCore import QEvent
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    before = list(app.topLevelWidgets()) if isinstance(app, QApplication) else []
    yield
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        return
    victims = [w for w in app.topLevelWidgets() if not any(w is b for b in before)]
    del before
    for w in victims:
        try:
            w.close()
        except RuntimeError:
            pass
    for w in victims:
        try:
            w.deleteLater()
        except RuntimeError:
            pass
    for w in victims:
        try:
            QApplication.sendPostedEvents(w, QEvent.Type.DeferredDelete)
        except RuntimeError:
            pass