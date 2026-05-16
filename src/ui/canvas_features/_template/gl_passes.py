"""
GL render passes for this feature.

Each pass is auto-discovered by ``gl_pass_registry.py``.
Export a ``GL_RENDER_PASSES`` list of ``CanvasGLRenderPass`` instances.

Set ``stack_role`` to a ``CanvasStackRole`` — the central stacking policy
resolves it to a concrete ``(RenderPhase, priority)``.  Do NOT hardcode
``layer`` or ``priority`` directly.
"""

from __future__ import annotations

from ui.canvas_infra.scene.gl_pass_contract import CanvasGLRenderPass
from ui.canvas_infra.scene.stacking_policy import CanvasStackRole

GL_RENDER_PASSES: list[CanvasGLRenderPass] = [

]
