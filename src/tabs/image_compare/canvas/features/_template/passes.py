"""
Render passes for this feature.

Each pass is auto-discovered by ``pass_registry.py``.
Export a ``RENDER_PASSES`` list of ``CanvasRenderPassBase`` instances.

Set ``stack_role`` to a ``CanvasStackRole`` — the central stacking policy
resolves it to a concrete ``(RenderPhase, priority)``.  Do NOT hardcode
``layer`` or ``priority`` directly.
"""

from __future__ import annotations

from ui.canvas_infra.scene.pass_contract import CanvasRenderPassBase

RENDER_PASSES: list[CanvasRenderPassBase] = []
