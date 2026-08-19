"""Contract: src/ui/ must not import specific tab packages.

The ``src/ui/`` tree is host infrastructure.  It may import from
``tabs.contract`` and ``tabs.registry`` (the shared tab boundary), but
NEVER from specific tab packages like ``tabs.image_compare``,
``tabs.multi_compare``, etc.  Such imports leak tab internals into the
host and break lazy initialization.

Dogma source: docs/dev/ARCHITECTURE.md, docs/dev/CONTRACTS.md
"""

from __future__ import annotations

import re
from pathlib import Path

from tests.contracts._framework import SRC, iter_py, rel

# Allowed imports from the tabs package — the shared boundary
_ALLOWLISTED_TAB_IMPORTS = re.compile(
    r"^(?:src\.)?tabs\.(contract|registry)\b"
)

# Specific tab packages that must NEVER be imported from src/ui/
_TAB_PACKAGES = re.compile(
    r"^(?:src\.)?tabs\.(image_compare|multi_compare|session_picker|image_gallery)\b"
)


def test_ui_does_not_import_specific_tab_packages():
    """src/ui/ must not import from specific tab packages."""
    offenders: list[str] = []
    ui_dir = SRC / "ui"
    for path in iter_py(ui_dir):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        rel_path = rel(path)
        for node in ast.walk(tree):
            module = None
            if isinstance(node, ast.ImportFrom) and node.module:
                module = node.module
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    module = alias.name
            if module is None:
                continue
            if _TAB_PACKAGES.match(module):
                if not _ALLOWLISTED_TAB_IMPORTS.match(module):
                    offenders.append(f"{rel_path}:{node.lineno} imports '{module}'")
    assert not offenders, (
        "src/ui/ imports specific tab packages (sandbox violation):\n  "
        + "\n  ".join(offenders)
    )


import ast
