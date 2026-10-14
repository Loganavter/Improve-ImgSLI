"""Shared pytest configuration for the test suite.

Adds ``src/`` to ``sys.path`` so tests can import application modules without
per-file boilerplate. External packages, including ``sli-ui-toolkit``, must be
installed through the requirements files.
"""

from __future__ import annotations

import os
import sys

# Headless CI / agent runs: avoid requiring a display for PySide6 widgets.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))

for _entry in (os.path.join(_REPO, "src"),):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)


import pytest
from sli_ui_toolkit.config import reset_toolkit_config

from tabs import registry as _tabs_registry_module


@pytest.fixture(autouse=True)
def _reset_toolkit_config():
    """configure_toolkit state is process-wide; isolate every test from it.

    ``ui.icon_manager`` (imported at module scope by some tests) calls
    ``configure_toolkit`` with the app's flyout defaults (e.g.
    ``default_flyout_animation="fade"``); without a reset that leaks into
    every later test in the same process and makes flyout show/hide timing
    nondeterministic (a "fade"-animated flyout hides 150 ms after hide()).
    """
    reset_toolkit_config()
    yield
    reset_toolkit_config()


@pytest.fixture(autouse=True)
def _destroy_lingering_toplevels():
    """Deterministically destroy lingering top-levels at teardown (suite-wide).

    CI segfaults (``Fatal Python error: Segmentation fault`` in
    ``pytestqt/plugin.py:_process_events`` under ``-n 8``) come from test
    windows outliving their test: ``qtbot`` teardown (``close()`` +
    ``deleteLater()``) never delivers ``DeferredDelete`` on the offscreen
    QPA, so the dialog leaks — alive, with app-wide event filters / signal
    connections keeping stale receivers installed. The next test's ``show()``
    queues window-system focus events; a later ``processEvents`` then
    notifies through the stale receiver after shiboken freed the C++ object
    (``getWrapperForQObject`` → SIGSEGV).

    This fixture closes the leak: at teardown every top-level widget created
    during the test is closed and its ``DeferredDelete`` delivered
    synchronously, so C++ destruction happens deterministically while Python
    wrappers are still alive. Mirrors
    ``tests/runtime/conftest.py::_destroy_lingering_toplevels`` (kept as-is;
    harmless duplication beats shared-import coupling across conftest scopes).

    Only widgets created *during* the test are destroyed (setup snapshot).
    """
    from PySide6.QtCore import QEvent
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    # Strong refs: keep setup-time windows alive for the whole test so
    # their later teardown below compares by identity, not id().
    before = list(app.topLevelWidgets()) if app is not None else []
    yield
    app = QApplication.instance()
    if app is None:
        return
    victims = [w for w in app.topLevelWidgets() if not any(w is b for b in before)]
    # Drop the setup refs first: widgets the test itself abandoned are
    # already half-torn-down or dead — only C++ destruction matters now.
    del before
    for w in victims:
        try:
            w.close()
        except RuntimeError:
            # Wrapper already dead (C++ gone with it) — nothing to do.
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
    # NOTE: no processEvents() here on purpose — pytest-qt's own
    # teardown hook drains the loop after all fixture finalizers, with
    # stale receivers already destroyed above.
    if not _sweep_all_destroyed(victims):
        import warnings

        warnings.warn(
            "lingering top-level widgets survived the teardown sweep; "
            "cross-test Qt state may leak",
            RuntimeWarning,
            stacklevel=2,
        )


def _sweep_all_destroyed(widgets) -> bool:
    """Best-effort check the sweep really destroyed everything (debug aid).

    Never fails the suite: returns True unless a *live* widget remains.
    """
    import shiboken6
    from PySide6.QtWidgets import QApplication

    for w in widgets:
        try:
            if shiboken6.isValid(w) and w in QApplication.instance().topLevelWidgets():
                return False
        except RuntimeError:
            continue
    return True


@pytest.fixture(autouse=True)
def _reset_translation_language():
    """Global current language is process-wide; isolate every test from it.

    Tests that switch the live language (``emit_language_changed("ru")``)
    restore it in their own ``finally``, but tests under ``src/tabs/`` (which
    use a different conftest) don't always, and a ``tr(...)`` fallback
    assertion (``ColorPickerDialog`` OK button == "OK", multi-compare footer
    tooltip containing "grid") breaks when the previous test left the
    language at non-English. Force English both before and after every test.
    """
    import resources.translations as _translations

    _force_language(_translations, "en")
    try:
        yield
    finally:
        _force_language(_translations, "en")


def _force_language(translations, lang: str) -> None:
    """Set the manager's live language + loaded pack without emitting."""
    translations._manager._current_lang = lang
    translations._manager._translations = translations._manager.ensure_loaded(lang)


@pytest.fixture(autouse=True)
def _reset_theme_manager():
    """ThemeManager is a process-wide singleton; isolate every test from it.

    Theme-dialog tests (``test_app_message_dialog_theme`` etc.) register
    palettes + QSS on the singleton and never unregister them. The QSS changes
    font metrics, so a later test that builds a sizeHint-driven dialog
    (e.g. ``ColorPickerDialog``) gets a wider minimum size and its geometry
    assertions break. Snapshot-and-restore the singleton's mutable state
    around every test, mirroring ``_reset_toolkit_config``.

    The same tests also install the app-wide CSD decoration event filter
    (``install_application_dialog_decorations``), which auto-decorates every
    top-level ``QDialog`` at Polish time and stays installed process-wide.
    Uninstall it too, otherwise later dialog-geometry tests (color picker,
    …) silently gain a title bar and their sizeHint/right-alignment asserts
    break.
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
        tm._current_theme, tm._light_palette, tm._dark_palette, tm._qss_template, qss_paths = saved
        tm._qss_paths = qss_paths
        app = QApplication.instance()
        if app is not None and app.styleSheet():
            app.setStyleSheet("")
        if app is not None and getattr(app, "_csd_filter_installed", False):
            csd_filter = getattr(app, "_csd_filter", None)
            if csd_filter is not None:
                app.removeEventFilter(csd_filter)
            app._csd_filter_installed = False  # type: ignore[attr-defined]
            app._csd_filter = None  # type: ignore[attr-defined]


@pytest.fixture(autouse=True)
def _reset_navigation_manager():
    """``NavigationManager`` is a process-wide toolkit singleton; isolate tests.

    ``tests/test_navigation_manager.py`` installs a test instance as
    ``NavigationManager._instance`` and never restores it. The leaked manager
    keeps an active section that intercepts arrow keys, so a later tab test's
    ``Key_Down`` never reaches the widget's own handler (session-picker header →
    recent-items handoff), which fails only in combined runs. Reset the singleton
    around every test.
    """
    from sli_ui_toolkit.managers import NavigationManager

    def _clear() -> None:
        mgr = NavigationManager._instance
        if mgr is not None:
            # The manager installs itself as an app-wide event filter; clearing
            # only ``_instance`` leaves it intercepting arrow keys app-wide.
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
    ``~/.cache/<app>/pixel_tile_store``, so every store built without an
    explicit ``tmp_dir`` would litter the real cache. Redirect the
    process-wide spill-dir cache to the session tmp dir instead; tests that
    pass their own ``tmp_dir`` are unaffected (``tmp_dir`` wins in
    ``_spill_dir``).
    """
    from engine.store import tiled_pixel_store as _tps

    monkeypatch.setattr(_tps, "_spill_dir_cache", _hermetic_tps_spill_dir)


@pytest.fixture(autouse=True)
def _restore_tab_registry_singletons():
    """Restore the process-wide TabRegistry singletons around every test.

    Discovery-isolation tests replace ``TabRegistry._instance`` with a fresh
    registry (``test_staged_tab_discovery``, ``test_workspace_session_
    activation``). That detaches the class singleton from the hot-path
    ``_shared_registry``: later tests that route through ``TabRegistry()``
    (e.g. ``execute_canvas_feature_alias`` in the video-editor keyframing
    adapters) then resolve against an instance whose ``_active_session_type``
    is None instead of the one the test fixture activated — commands
    silently no-op and the test fails with an empty tool list. Snapshot and
    restore both singletons plus their mutable mapping state so the
    app-lifetime instances always survive.
    """
    saved_instance = _tabs_registry_module.TabRegistry._instance
    saved_shared = _tabs_registry_module._shared_registry
    saved_state = _snapshot_registry(saved_instance)
    saved_shared_state = _snapshot_registry(saved_shared)
    try:
        yield
    finally:
        _tabs_registry_module.TabRegistry._instance = saved_instance
        _tabs_registry_module._shared_registry = saved_shared
        _restore_registry(saved_instance, saved_state)
        _restore_registry(_tabs_registry_module._shared_registry, saved_shared_state)


def _snapshot_registry(registry):
    """Shallow snapshot of a registry's mutable discovery state (or None).

    Same objects, restored mappings: reverts every ``_tabs``/``_pending``
    injection (``recording``/``fake``/``intruder`` junk) and every
    ``dispose_all`` wipe, so the next test in the worker never inherits
    foreign or missing tabs (CI ambient red, lazy_init ``fake`` missing,
    contracts ``_Tab is not a TabContract``).
    """
    if registry is None:
        return None
    return {
        "tabs": dict(registry._tabs),
        "pages": dict(registry._pages),
        "pending": dict(registry._pending_pages),
        "tiers": set(registry._discovered_tiers),
        "stale": set(registry._appearance_stale),
        "active_type": registry._active_session_type,
        "active_id": registry._active_session_id,
        "context": registry._context,
    }


def _restore_registry(registry, saved) -> None:
    """Restore a snapshot taken by ``_snapshot_registry``."""
    if registry is None or saved is None:
        return
    registry._tabs.clear()
    registry._tabs.update(saved["tabs"])
    registry._pages.clear()
    registry._pages.update(saved["pages"])
    registry._pending_pages.clear()
    registry._pending_pages.update(saved["pending"])
    registry._discovered_tiers.clear()
    registry._discovered_tiers.update(saved["tiers"])
    registry._appearance_stale.clear()
    registry._appearance_stale.update(saved["stale"])
    registry._active_session_type = saved["active_type"]
    registry._active_session_id = saved["active_id"]
    registry._context = saved["context"]
