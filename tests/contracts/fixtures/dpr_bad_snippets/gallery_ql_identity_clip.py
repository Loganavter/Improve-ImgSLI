# provenance: src/tabs/image_gallery/ui/quick_look/preview_canvas/rhi_entry.py:270 @ b58ea02ac^ (parent of #752)
# rule: clip-matrix-literal
"""RED fixture: the Quick Look preview stood an identity clip matrix in.

The shipped code (verbatim names, comments trimmed) uploaded the raster and
staged a hardcoded identity `mat4`, so on a backend whose clip space is y-down
(Vulkan) the preview came out mirrored. It only looked right on the host the
author used — the exact reason rule 1 exists: an identity is a *claim* about
the backend, and the claim belongs to `engine/gpu/rt_y_orientation`.
"""

from __future__ import annotations

# Identity clip matrix for the fullscreen shell quad (the preview has no
# viewport transform -- aspect-fit is baked into the uploaded raster).
_IDENTITY_CLIP = (
    1.0, 0.0, 0.0, 0.0,
    0.0, 1.0, 0.0, 0.0,
    0.0, 0.0, 1.0, 0.0,
    0.0, 0.0, 0.0, 1.0,
)


class PreviewEntry:
    def __init__(self, shell) -> None:
        self._shell = shell

    def _render_raster(self, command_buffer, target, updates) -> None:
        self._shell.stage_quad(updates)
        self._shell.stage_clip(updates, _IDENTITY_CLIP)
