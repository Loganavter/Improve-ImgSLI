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
    from shared.image_processing import tiled_pixel_store as _tps

    monkeypatch.setattr(_tps, "_spill_dir_cache", _hermetic_tps_spill_dir)