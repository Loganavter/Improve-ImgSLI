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
    from shared.image_processing import tiled_pixel_store as _tps

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
    restore both singletons so the app-lifetime instances always survive.
    """
    saved_instance = _tabs_registry_module.TabRegistry._instance
    saved_shared = _tabs_registry_module._shared_registry
    try:
        yield
    finally:
        _tabs_registry_module.TabRegistry._instance = saved_instance
        _tabs_registry_module._shared_registry = saved_shared