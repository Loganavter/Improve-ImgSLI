"""Shared code must not import ``tabs.image_compare.canvas.features.<name>`` directly.

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
    r"(?:from|import)\s+(?:src\.)?tabs\.image_compare\.canvas\.features\.([a-zA-Z_][\w]*)"
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


def test_plan_applicator_uses_tab_services_for_live_feature_hooks():
    path = SRC / "ui" / "canvas_presentation" / "plan_applicator.py"
    text = read(path)
    forbidden = (
        "get_canvas_feature_command",
        "apply_canvas_feature_live_runtime_overlays",
        "splitter.sync_split_position",
        "set_guides_params",
        "set_capture_color",
        "set_pil_layers",
        "reset_view",
        "_stored_pil_images",
        "source_image1",
        "source_image2",
        "apply_legacy_canvas_render_plan",
    )
    hits = [token for token in forbidden if token in text]
    assert not hits, (
        "plan_applicator.py must route live feature hooks through tab services: "
        f"{hits}"
    )
