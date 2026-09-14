"""Phase-A0 render-pass manifest for the image_compare base-image stage.

Mirrors ``tabs/multi_compare/scene/passes/base_images.py`` (Phase-2 pass
shape) exactly: module-level ``RENDER_PASSES`` + per-pass ``stack_role`` /
``visibility`` class attrs, order identical to the live renderer wiring
(base-image array draw first, registry-discovered feature passes after --
see ``RhiCanvasRenderer.render`` in ``renderer.py`` and ``submit_array_draw``
in ``use_cases/draw.py``, which records feature passes only after the base
array plan is drawn).

Declaration only, zero behavior change: the live renderer still wires the
base-image draw directly (``renderer.py``); this list is the declaration
point for routing it through the ordered pass set later. Nothing at runtime
consumes this list yet besides ``tests/contracts/test_ic_render_manifest.py``.
"""

from __future__ import annotations

from ui.canvas_infra.scene.pass_contract import CanvasRenderPassBase, SceneVisibility
from ui.canvas_infra.scene.stacking_policy import CanvasStackRole

__all__ = [
    "BaseImagesPass",
    "RENDER_PASSES",
]


class BaseImagesPass(CanvasRenderPassBase):
    """Declarative manifest of the base-image array-draw stage.

    Forward-shape declaration for routing through
    ``iter_active_render_passes`` / ``iter_ordered_render_passes``: the
    base-image stage draws the pair content every frame (same role as
    multi_compare's ``BaseImagesPass`` until the stacking policy gains a
    dedicated base role, if ever). The live renderer still wires the
    array draw directly (see ``renderer.py``) -- this class only declares
    order via ``stack_role`` and scope via ``visibility``.

    Never instantiated by the renderer; ``record()`` / ``paint()`` are
    intentionally not implemented (inherited ``CanvasRenderPassBase``
    defaults apply). ``record()`` reads only its context plus prepared
    state -- no widget/store access, no export-mode branches
    (snapshot-replay per rendering-model).
    """

    stack_role = CanvasStackRole.IMAGE_OVERLAY_CONTENT
    visibility = SceneVisibility.ALL


# Phase-A0 manifest (mirrors multi_compare's scene base pass): the live
# renderer still owns its base-image draw directly (see ``renderer.py``) --
# this list is the declaration point for routing it through the ordered
# pass set later. Single entry, first by wiring order.
RENDER_PASSES: list[CanvasRenderPassBase] = [BaseImagesPass()]
RENDER_PASSES = RENDER_PASSES
