# provenance: src/tabs/image_compare/canvas/features/drag_drop_overlay/passes.py:288 @ 167b9d820^ (parent of #751)
# rule: viewport-logical
"""RED fixture: device-pixel NAMES holding LOGICAL numbers.

Verbatim shape of pre-#751 `record()`: `ctx.framebuffer_size` is absent in
image_compare, so `fb_w`/`fb_h` were filled from the context's LOGICAL
`width`/`height` and the pass then drew the device-pixel raster into that
viewport — a quarter of the framebuffer area at DPR=2 ("the zone gets smaller at
a larger interface scale"). A pure name check cannot see this: the names say
device, the values are logical. Rule `viewport-logical` therefore also flags a
device-NAMED variable assigned from a non-device expression.
"""

from __future__ import annotations


class DragDropOverlayPass:
    def __init__(self) -> None:
        self._shell = None

    def record(self, command_buffer, widget, ctx) -> None:
        host = widget
        # ctx.framebuffer_size may not exist; fallback to width/height
        fb = getattr(ctx, "framebuffer_size", None)
        if fb is None:
            width = int(
                getattr(ctx, "width", 0) or getattr(host, "width", lambda: 0)() or 800
            )
            height = int(
                getattr(ctx, "height", 0) or getattr(host, "height", lambda: 0)() or 600
            )
            # Account for DPR later via painter.scale
            fb_w, fb_h = width, height
        else:
            fb_w, fb_h = fb
        self._shell.draw(command_buffer, width=float(fb_w), height=float(fb_h))
