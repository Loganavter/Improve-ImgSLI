from __future__ import annotations

import logging

_log = logging.getLogger("ImproveImgSLI.magnifier.gl_surface")

from .plan_builder import build_canvas_plan, build_live_store_presentation

def apply_store_to_gl_canvas(
    canvas,
    store,
    image1,
    image2,
    *,
    fit_content: bool = False,
    source_image1=None,
    source_image2=None,
    source_key=None,
    display_cache_key=None,
    clip_overlays_to_image_bounds: bool = False,
):
    from ui.canvas_presentation.plan_applicator import apply_canvas_render_plan

    presentation = build_live_store_presentation(store)
    display_image1 = image1 or presentation.display_image1
    display_image2 = image2 or presentation.display_image2
    source_image1 = source_image1 or presentation.source_image1
    source_image2 = source_image2 or presentation.source_image2
    source_key = source_key or presentation.source_key
    display_cache_key = (
        display_cache_key
        if display_cache_key is not None
        else presentation.display_cache_key
    )

    plan = build_canvas_plan(
        store,
        display_image1,
        display_image2,
        source_image1=source_image1,
        source_image2=source_image2,
        source_key=source_key,
        display_cache_key=display_cache_key,
        preserve_zoom=True,
    )

    apply_canvas_render_plan(
        canvas,
        plan,
        store=store,
        clip_overlays_to_image_bounds=clip_overlays_to_image_bounds,
    )
