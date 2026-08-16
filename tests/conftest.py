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