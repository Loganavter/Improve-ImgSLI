# provenance: src/tabs/image_compare/canvas/features/drag_drop_overlay/framing.py:56 @ 230431a52
# rule: none
"""LEGAL fixture: a viewport sized from the framebuffer, in two steps.

Verbatim shape from `framing.framebuffer_size` + a `record()`. The size reaches
the viewport through names assigned from `ctx.framebuffer_size` and
`renderTarget().pixelSize()`, which is exactly what rule `viewport-logical`
requires; a name-based or "is it a parameter" heuristic would flag it, the
mini-taint must not.

Contrast `viewport_logical_ctx_size.py`: same function shape, `ctx.width`
instead of the framebuffer.
"""

from __future__ import annotations

from PySide6.QtGui import QRhiViewport


def framebuffer_size(host, ctx):
    fb = getattr(ctx, "framebuffer_size", None)
    if fb is not None:
        return int(fb[0]), int(fb[1])
    target = host.renderTarget()
    size = target.pixelSize()
    return int(size.width()), int(size.height())


class DropOverlayPass:
    def record(self, command_buffer, widget, ctx) -> None:
        fb_w, fb_h = framebuffer_size(widget, ctx)
        viewport = QRhiViewport(0.0, 0.0, float(fb_w), float(fb_h))
        command_buffer.setViewport(viewport)
        command_buffer.draw(4)
