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
