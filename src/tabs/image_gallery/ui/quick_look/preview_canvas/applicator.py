"""Quick-look canvas: shared-applicator render plan.

Split from ``preview_canvas.py`` (plan-gallery-split-2026-10-17, Part C2).
Bodies moved verbatim; names and signatures unchanged. Plain functions
take the canvas widget as their first argument (``CODE_PATTERNS.md`` --
thin owner + module functions).
"""

from __future__ import annotations

import logging

from ui.canvas_presentation.composition import LayerNode
from ui.canvas_presentation.plan import CanvasRenderPlan
from ui.canvas_presentation.plan_applicator import apply_canvas_render_plan
from core.log_names import APP_LOGGER_NAME

logger = logging.getLogger(APP_LOGGER_NAME)


# -- shared-applicator plan -------------------------------------------------


def _refresh_plan(self) -> None:
    """Single-LayerNode plan via the shared applicator (only apply path)."""
    try:
        store = self._store
        if store is None:
            self._active_composition = None
            self._active_render_plan = None
            return
        try:
            canvas_w = max(1, int(self.width()))
            canvas_h = max(1, int(self.height()))
        except Exception:
            canvas_w, canvas_h = 1, 1
        plan = CanvasRenderPlan(
            image1=None,
            image2=None,
            source_image1=None,
            source_image2=None,
            source_key=(),
            canvas_w=canvas_w,
            canvas_h=canvas_h,
            render_scene=None,
            overlay_layout=None,
            capture_visible=False,
            capture_color=None,
            guides_enabled=False,
            guides_color=None,
            guides_thickness=0,
            composition_root=LayerNode(layer_id=0, image=store, fit_mode="contain"),
        )
        apply_canvas_render_plan(self, plan)
    except Exception:
        logger.debug("QuickLook preview: plan refresh failed open", exc_info=True)
