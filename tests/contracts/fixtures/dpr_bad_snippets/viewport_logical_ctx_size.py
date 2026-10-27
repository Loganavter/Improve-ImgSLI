# provenance: src/tabs/image_compare/canvas/features/magnifier/render/magnifier_pass.py:1022 @ reconstructed
# rule: viewport-logical
"""RED fixture: a viewport sized from the LOGICAL context width/height.

Reconstructed from the #751 shape (`167b9d820^`, image_compare's drop overlay):
the render context carries LOGICAL `width`/`height`, and a viewport built from
them draws the device-pixel raster into `1/DPR` of the framebuffer per axis — a
quarter of the area at DPR=2, i.e. the owner report "the zone gets *smaller* at
a larger interface scale".

The repaired form asks the framebuffer, once, through
`drag_drop_overlay/framing.py::framebuffer_size` (prefer
`ctx.framebuffer_size`, else `renderTarget().pixelSize()`, else logical * DPR);
the negative fixture `legal_framebuffer_viewport.py` is that shape.
"""

from __future__ import annotations

from PySide6.QtGui import QRhiViewport


class MagnifierPass:
    def record(self, command_buffer, widget, ctx) -> None:
        command_buffer.setGraphicsPipeline(self.pipeline)
        width = getattr(ctx, "width", 0)
        height = getattr(ctx, "height", 0)
        viewport = QRhiViewport(0.0, 0.0, float(width), float(height))
        command_buffer.setViewport(viewport)
        command_buffer.draw(4)
