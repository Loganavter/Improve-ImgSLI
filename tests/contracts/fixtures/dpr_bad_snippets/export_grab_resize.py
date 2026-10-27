# provenance: src/engine/gpu/export_tiling.py:123 @ 230431a52
# rule: silent-downsample
"""RED fixture: a DEVICE-pixel grab resized to a LOGICAL target.

Verbatim `_render_single` body from the current tree. The grab is device pixels
(`grabFramebuffer`), the target is the plan's device-INDEPENDENT export size, so
on a HiDPI host this resize halves the resolution — silently, because the
result still has the request.  It is allowlisted in the tree with the measured
reason ("supersample downscale", see
`test_export_grab_downscale_preserves_content`), and it stays a DETECTOR because
the pattern is one `_last_size` edit away from a real resolution loss.
"""

from __future__ import annotations


class TiledFramebufferExporter:
    def _render_single(self, canvas_w: int, canvas_h: int):
        target = (canvas_w, canvas_h)
        qimg = self._widget.grabFramebuffer()
        image = qimage_to_pil_rgba(qimg)
        if image.size != target:
            image = image.resize(target, None)
        return image


def qimage_to_pil_rgba(qimg):
    return qimg
