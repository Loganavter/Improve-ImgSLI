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


class SceneVisibility(Flag):
    INTERACTIVE = auto()
    EXPORT = auto()
    PREVIEW = auto()
    ALL = INTERACTIVE | EXPORT | PREVIEW


class CanvasRenderPassBase:
    """
    A feature-owned GL render pass.

    Features declare their passes in ``tabs/<tab>/canvas/features/<name>/passes.py``
    and export them as ``RENDER_PASSES``.  The registry discovers them
    automatically; ``render_passes.py`` calls them in layer/priority order.

    Pass instances are persistent across frames.  Store compiled shader
    programs and other GL resources as instance attributes.

    Set ``stack_role`` to a :class:`CanvasStackRole` value. The central
    stacking policy resolves it to ``(RenderPhase, priority)``.
    """

    stack_role = None
    visibility: SceneVisibility = SceneVisibility.ALL

    def resolved_layer_and_priority(self) -> tuple[RenderPhase, int]:
        """Return concrete ``(RenderPhase, priority)`` for this pass.

        Delegates to the central stacking policy. Feature passes must declare
        ``stack_role``; raw layer/priority attributes are not supported.
        """
        if self.stack_role is None:
            raise ValueError(f"{type(self).__name__} must declare stack_role")
        from .stacking_policy import resolve_render_pass_order

        return resolve_render_pass_order(self.stack_role)

    def initialize(self, widget) -> None:
        """Called once after the render context is ready."""

    def should_paint(self, ctx) -> bool:
        """Return ``True`` if this pass has anything to draw this frame."""
        return True

    def paint(self, widget, ctx) -> None:
        """Issue draw calls for this pass."""
        raise NotImplementedError(f"{type(self).__name__}.paint() is not implemented")

    def cleanup(self, widget) -> None:
        """Called on GL context destruction.  Release shader programs and textures."""


class CanvasRenderPass(CanvasRenderPassBase):
    """Feature-owned QRhi pass recorded into the canvas command buffer."""

    def initialize(self, rhi, target) -> None:
        """Create persistent QRhi resources for this render target."""

    def prepare(self, widget, ctx, resource_updates) -> None:
        """Queue per-frame buffer/texture updates before ``beginPass``."""

    def record(self, command_buffer, widget, ctx) -> None:
        """Record draw commands inside the active QRhi render pass."""
        raise NotImplementedError(f"{type(self).__name__}.record() is not implemented")

    def release(self) -> None:
        """Destroy persistent QRhi resources."""


def is_single_image_preview_scene(ctx) -> bool:
    return bool(
        int(getattr(getattr(ctx, "scene_frame", None), "single_image_preview", 0) or 0)
    )
