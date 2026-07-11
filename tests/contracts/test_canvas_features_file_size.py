"""Canvas feature file-size / cohesion dogma.

A canvas feature file may exceed the soft line limit only if it says why it
can't be split further. Without this, the existing structural contracts
(manifest exports the right name, passes.py exports RENDER_PASSES, etc.) are
all satisfied by a single 800+ line file that mixes unrelated
responsibilities — the file-*role* contracts in
docs/dev/QRHI_CANVAS_FEATURES.md never constrained what goes *inside* a role.

Rule: a ``.py`` file inside a canvas feature package longer than
``LINE_LIMIT`` must contain a ``File-Size-Exempt:`` marker (in a comment or
docstring) explaining why it isn't split further — e.g. "single QRhi pass,
one resource lifecycle" (see
``tabs/image_compare/canvas/features/magnifier/magnifier_pass.py``). A file
without the marker is either genuinely unsplit debt (fix it) or missing its
justification (add the marker).

Dogma source: docs/dev/QRHI_CANVAS_FEATURES.md, "File size & cohesion".
"""

from __future__ import annotations

import pytest

from ._framework import list_all_canvas_features, read, rel

LINE_LIMIT = 400
_MARKER = "File-Size-Exempt:"

def _feature_py_files(feature):
    return [
        p
        for p in feature.rglob("*.py")
        if "__pycache__" not in p.parts and "tests" not in p.parts
    ]

FEATURES = list_all_canvas_features()
FEATURE_IDS = [f.name for f in FEATURES]

@pytest.mark.parametrize("feature", FEATURES, ids=FEATURE_IDS)
def test_oversized_files_declare_exemption(feature):
    violations = []
    for path in _feature_py_files(feature):
        src = read(path)
        line_count = src.count("\n") + 1
        if line_count <= LINE_LIMIT:
            continue
        if _MARKER in src:
            continue
        violations.append(f"{rel(path)} ({line_count} lines)")
    assert not violations, (
        f"file(s) over {LINE_LIMIT} lines with no '{_MARKER}' justification "
        f"— split it, or add the marker with a one-line reason it can't be "
        f"split further:\n  - " + "\n  - ".join(violations)
    )
