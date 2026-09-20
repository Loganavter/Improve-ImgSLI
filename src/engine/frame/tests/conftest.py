# Audit-Meta: pattern=test-bootstrap reason="sys.path shim so frame tests run standalone"
"""Make ``src/engine/frame/tests`` runnable standalone.

Puts ``src/`` on ``sys.path`` so tests import ``engine.frame...`` the
same way the top-level suite does via its own root conftest. Without
this, running this directory in isolation fails with
``ModuleNotFoundError: No module named 'engine'`` — pytest's own
package-insertion adds the repo root (the full ``__init__`` chain from
``src`` down to ``tests`` exists), not ``src/``.
"""

from __future__ import annotations

import os
import sys

_SRC = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, os.pardir)
)

if _SRC not in sys.path:
    sys.path.insert(0, _SRC)
