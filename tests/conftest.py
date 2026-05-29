"""Shared pytest configuration for the test suite.

Adds ``src/`` and the bundled ``sli-ui-toolkit`` package to ``sys.path`` so
tests can ``from ui.… import …`` and ``from sli_ui_toolkit.… import …``
without per-file boilerplate.
"""

from __future__ import annotations

import os
import sys

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))

for _entry in (
    os.path.join(_REPO, "src"),
    os.path.join(_REPO, "packages", "sli-ui-toolkit", "src"),
):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)
