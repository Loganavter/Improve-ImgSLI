"""Shared code must not import ``ui.canvas_features.<name>`` directly.

Allowed importers: other canvas features (peer-to-peer is OK) and
``canvas_infra`` (the auto-discovery framework itself).

Dogma source: docs/dev/CANVAS_FEATURES.md ("No imports of this feature in
shared ui/, events/, or plugins/ code"); CONTRACTS.md ("No direct imports
of features in shared code").
"""

from __future__ import annotations

import re

from ._framework import (
    CANVAS_FEATURES,
    CANVAS_INFRA,
    SRC,
    iter_py,
    read,
    rel,
)

_IMPORT_RE = re.compile(
    r"(?:from|import)\s+(?:src\.)?ui\.canvas_features\.([a-zA-Z_][\w]*)"
)

def test_no_canvas_feature_imports_in_shared_code():
    allowed = (CANVAS_FEATURES, CANVAS_INFRA)
    leaks: list[str] = []
    for py in iter_py(SRC):
        if any(str(py).startswith(str(r)) for r in allowed):
            continue
        for i, line in enumerate(read(py).splitlines(), 1):
            m = _IMPORT_RE.search(line)
            if not m:
                continue
            fname = m.group(1)
            if fname.startswith("_"):
                continue
            leaks.append(
                f"{rel(py)}:{i} imports canvas feature '{fname}' "
                f"(use capability aliases)"
            )
    assert not leaks, "\n  - " + "\n  - ".join(leaks)
