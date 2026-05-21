from __future__ import annotations

from enum import Flag, IntEnum, auto

class RenderPhase(IntEnum):
    """
    Ordered render phases for GL feature passes.
    """

    BASE_IMAGE = 0
    IMAGE_DECORATION = 10
    IMAGE_ANNOTATION = 20
    VIEW_ANNOTATION = 30
    HUD = 40
    DEBUG = 50

CanvasGLLayer = RenderPhase

class SceneVisibility(Flag):
    INTERACTIVE = auto()
    EXPORT = auto()
    PREVIEW = auto()
    ALL = INTERACTIVE | EXPORT | PREVIEW

class CanvasGLRenderPass:
    """
    A feature-owned GL render pass.

    Features declare their passes in ``canvas_features/<name>/gl_passes.py``
    and export them as ``GL_RENDER_PASSES``.  The registry discovers them
    automatically; ``render_passes.py`` calls them in layer/priority order.

    Pass instances are persistent across frames.  Store compiled shader
    programs and other GL resources as instance attributes.

    Preferred: set ``stack_role`` to a :class:`CanvasStackRole` value.
    The central stacking policy resolves it to ``(RenderPhase, priority)``.

    Legacy: ``layer`` and ``priority`` class attributes are still honoured
    when ``stack_role`` is not set.
    """

    stack_role = None
    layer: RenderPhase = RenderPhase.VIEW_ANNOTATION
    priority: int = 100
    visibility: SceneVisibility = SceneVisibility.ALL

    def resolved_layer_and_priority(self) -> tuple[RenderPhase, int]:
        """Return concrete ``(RenderPhase, priority)`` for this pass.

        If ``stack_role`` is set, delegates to the central stacking policy.
        Otherwise falls back to the explicit ``layer``/``priority`` attributes.
        """
        if self.stack_role is not None:
            from .stacking_policy import resolve_gl_pass_order
            return resolve_gl_pass_order(self.stack_role)
        return (self.layer, self.priority)

    def initialize(self, widget) -> None:
        """Called once after the GL context is ready."""

    def should_paint(self, ctx) -> bool:
        """Return ``True`` if this pass has anything to draw this frame."""
        return True

    def paint(self, widget, ctx) -> None:
        """Issue draw calls for this pass."""
        raise NotImplementedError(f"{type(self).__name__}.paint() is not implemented")

    def cleanup(self, widget) -> None:
        """Called on GL context destruction.  Release shader programs and textures."""

def is_single_image_preview_scene(ctx) -> bool:
    return bool(int(getattr(getattr(ctx, "scene_frame", None), "single_image_preview", 0) or 0))
