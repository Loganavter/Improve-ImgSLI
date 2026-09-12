# Audit-Meta: pattern=derived-state reason="single Store snapshot → GPU commit barrier, fixes shadow cache divergence (store-redux-dogma)"
"""Derived GPU state — single commit barrier for Image Compare.

Systemic fix for divergence between Store (Redux) wish and GPU reality
(left-on-both, log lie, tiny bbox 0.001):

* Store is the only source of truth (docs/dev/STORE.md, CONTRACTS.md).
* CanvasRuntimeState / TileTextureService / RhiRenderer._last_good are
  imperative shadow caches mutated directly from widget (base_images.py,
  residency.py) outside Dispatcher — they survive Store undo/redo and are
  never validated.
* Previously `update_comparison_if_needed` re-read Store 3-4 times between
  `pick_display_with_preview_backing` and `upload_pil_images`, and
  `RhiRenderer.render` re-derived `is_same` from `widget.runtime_state`
  one frame late (`_prev_sources_is_same` lag).

This module computes a single immutable snapshot after `pick` and passes it
depth — no re-read, no shadow write outside the barrier.

See docs/dev/CONTRACTS.md three senses (interface/host sequence/dogma) and
docs/dev/tabs/index.md self-contained tab.
"""

from __future__ import annotations

from dataclasses import dataclass

from shared.image_processing.tiled_pixel_store import pixel_source_size
from shared.rendering.image_identity import image_uid


@dataclass(frozen=True)
class DerivedGpuState:
    """Immutable GPU commit derived from one Store snapshot.

    All fields are computed once in `update_comparison_if_needed` after picking
    display tier, then passed to `apply_store_to_canvas` → `upload_pil_images`
    → `realize_tile_plan` without re-reading Store or widget.runtime_state.
    """

    # display tier (stored role) — what base shader samples at 1x
    display_image1: object | None
    display_image2: object | None
    display_cache_key: tuple
    # source tier (hi-res for magnifier, zoom>1)
    source_image1: object | None
    source_image2: object | None
    source_key: tuple | None
    # identity
    is_same_object: bool
    source_changed: bool
    # geometry
    letterbox1: tuple[float, float, float, float]
    letterbox2: tuple[float, float, float, float]
    canvas_letterbox: tuple[float, float, float, float] | None


def build_derived_gpu_state(
    *,
    render_img1,
    render_img2,
    gui_source1,
    gui_source2,
    source_key: tuple | None,
    letterbox1,
    letterbox2,
    canvas_letterbox=None,
    prev_source_ids=None,
) -> DerivedGpuState:
    display_cache_key = (
        image_uid(render_img1),
        image_uid(render_img2),
        pixel_source_size(render_img1) if render_img1 is not None else None,
        pixel_source_size(render_img2) if render_img2 is not None else None,
    )
    is_same = bool(render_img1 is not None and render_img1 is render_img2)
    cur_ids = (image_uid(gui_source1), image_uid(gui_source2))
    source_changed = prev_source_ids is not None and cur_ids != prev_source_ids
    return DerivedGpuState(
        display_image1=render_img1,
        display_image2=render_img2,
        display_cache_key=display_cache_key,
        source_image1=gui_source1,
        source_image2=gui_source2,
        source_key=source_key,
        is_same_object=is_same,
        source_changed=source_changed,
        letterbox1=tuple(letterbox1) if letterbox1 is not None else (0.0, 0.0, 1.0, 1.0),
        letterbox2=tuple(letterbox2) if letterbox2 is not None else (0.0, 0.0, 1.0, 1.0),
        canvas_letterbox=tuple(canvas_letterbox) if canvas_letterbox is not None else None,
    )
