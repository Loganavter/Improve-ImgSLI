# provenance: src/tabs/image_compare/canvas/features/drag_drop_overlay/passes.py:252 @ 167b9d820^ (parent of #751)
# rule: clip-matrix-literal
"""RED fixture: the drop overlay fell back to an inline identity mat4.

Verbatim from the pre-#751 pass (docstring and imports dropped). The comment
says it out loud — "identity mat4" — and that is the defect: the pass had no
context matrix, so it invented one instead of asking
`engine/gpu/rt_y_orientation.composited_clip_correction`.
"""

from __future__ import annotations


class DragDropOverlayPass:
    def __init__(self) -> None:
        self._shell = None

    def prepare(self, widget, ctx, resource_updates) -> None:
        self._shell.stage_quad(resource_updates)
        # ctx.clip_matrix may not exist for image_compare; fallback to identity.
        clip_matrix = getattr(ctx, "clip_matrix", None)
        if clip_matrix is None:
            # identity mat4
            clip_matrix = (1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1)
        self._shell.stage_clip(resource_updates, clip_matrix)
