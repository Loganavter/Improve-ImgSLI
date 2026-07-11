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
