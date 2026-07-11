"""QRhi feature pass registry for the magnifier.

Must stay at the feature's top level: ``pass_registry`` auto-discovery
hardcodes an import of ``<feature>.passes`` (see
``src/ui/canvas_infra/scene/registry.py``) and silently skips features where
that import fails, so this file cannot be moved into ``render/``.

Three sub-passes are exported here for auto-discovery (see
``docs/dev/QRHI_CANVAS_FEATURES.md``, pass_registry). Their implementations
live in dedicated modules, split by shader/pipeline family rather than kept
in one file:

* ``arc_passes.py`` — ``OccludedArcPass`` / ``HiddenSelectionPass``, the two
  passes sharing the per-primitive arc shader.
* ``magnifier_pass.py`` — ``MagnifierPass``, the magnifier circle content
  (border-disk pipeline + uber ``mag`` pipeline). Kept as one class: it is
  one QRhi pass with one resource-lifecycle, not a bag of unrelated passes.
* ``passes_common.py`` / ``shader_layout.py`` — uniform packing and shader
  path/size constants shared by both of the above.

This module itself only wires ``RENDER_PASSES`` — never add pass logic here.
"""

from __future__ import annotations

from ui.canvas_infra.scene.pass_contract import CanvasRenderPass

from tabs.image_compare.canvas.features.magnifier.render.arc_passes import HiddenSelectionPass, OccludedArcPass
from tabs.image_compare.canvas.features.magnifier.render.magnifier_pass import MagnifierPass

__all__ = [
    "MagnifierPass",
    "OccludedArcPass",
    "HiddenSelectionPass",
    "RENDER_PASSES",
]

RENDER_PASSES: list[CanvasRenderPass] = [
    MagnifierPass(),
    OccludedArcPass(),
    HiddenSelectionPass(),
]
