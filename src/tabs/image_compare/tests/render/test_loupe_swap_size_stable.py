"""The loupe's drawn glass size is invariant under a swap inside the pair.

Owner report (2026-10-27, verbatim): "при swap внутри пары при включенной лупе …
размер увеличительных стекол немного подскакивает первые пары кадров, если одно
изображение меньше другого или наоборот, и затем возвращается".

The frames are reproduced offscreen, without a window, as the two states a swap
actually walks through on this pair:

1. **post-swap transient** — the display pair is the two per-side PREVIEWS
   (``bg_dirty.py`` forces preview/preview while the unified entry is missing
   because the unify cache key is order-sensitive), so slot 1 and slot 2 have
   *different* dimensions and aspects;
2. **settled** — the unified pair, both resampled to
   ``max(w1,w2) x max(h1,h2)``, so both sides have equal dimensions again.

Both frames run the real apply chain — the letterbox owner
(``update_common_letterbox_geometry``) then the tab's
``apply_plan_runtime_overlays`` → ``apply_magnifier_plan_overlay`` — and the
assertion reads the **widget-px glass radius** the renderer is handed
(``set_overlay_coords(..., overlay_radius)``), not counts, emits, or canvas-px
intermediates.

Invariant: the glass is sized from a pair-invariant reference (the comparison
envelope the letterbox is already fitted to), never from whichever slot-1
pixmap tier happened to be installed on that frame. Same-size pairs and
one-sided (have-gate) frames must not move at all.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PIL import Image

from core.state_management.dispatcher import Dispatcher
from core.store import Store
from core.store_viewport import SessionData
from tabs.image_compare.canvas.features.magnifier.state.store import (
    add_magnifier_model,
    set_default_magnifier_size,
    set_magnifier_enabled_flag,
)
from tabs.image_compare.canvas.presentation.plan_applicator import (
    apply_plan_runtime_overlays,
)
from tabs.image_compare.canvas.presentation.plan_builder import build_canvas_plan
from tabs.image_compare.canvas.texture_parts.base_images import (
    update_common_letterbox_geometry,
)
from tabs.image_compare.state.document import DocumentModel, ImageItem
from tabs.image_compare.state.models import (
    ImageSessionState,
    PipelineCacheState,
    RenderCacheState,
)

WIDGET = (1000, 800)

# Post-swap transient: each side's own preview (1024 long edge, aspect kept).
PREVIEW_LEFT = (1024, 576)   # landscape source
PREVIEW_RIGHT = (576, 1024)  # portrait source
# Settled: unify resamples both sides to the pair envelope.
UNIFIED = (1600, 1600)

SIZE_RELATIVE = 0.2


@pytest.fixture(autouse=True)
def _register_image_compare_canvas_features():
    from tabs.image_compare.tab import ImageCompareTab

    ImageCompareTab().register_canvas_features()


def _img(size, color):
    """Distinct content per side — same pixels would hide a slot mix-up."""
    return Image.new("RGBA", size, color)


def _store(img1, img2):
    import tabs.image_compare.bootstrap_reducers  # noqa: F401

    store = Store()
    store.create_workspace_session(session_type="image_compare", activate=True)
    paths = ("/gallery/left_landscape.png", "/gallery/right_portrait.png")
    store.set_session_state_slot(
        "document",
        DocumentModel(
            image_list1=[ImageItem(path=paths[0], display_name="a")],
            image_list2=[ImageItem(path=paths[1], display_name="b")],
            current_index1=0,
            current_index2=0,
        ),
    )
    store.viewport.session_data = SessionData(
        image_state=ImageSessionState(), render_cache=RenderCacheState()
    )
    store.state_changed = type(
        "Sig", (), {"emit": staticmethod(lambda *_a, **_k: None)}
    )()
    store.set_dispatcher(Dispatcher(store))
    store.set_session_state_slot("pipeline", PipelineCacheState())
    store.viewport.session_data.image_state.image1 = img1
    store.viewport.session_data.image_state.image2 = img2
    view_state = store.viewport.view_state
    set_magnifier_enabled_flag(view_state, True)
    set_default_magnifier_size(view_state, SIZE_RELATIVE)
    add_magnifier_model(view_state, store.viewport.render_config)
    return store


class _Canvas:
    """Just enough canvas for the legacy plan-apply surface.

    Records the widget-px overlay radius the magnifier pass receives.
    """

    def __init__(self, store):
        self._store = store
        self.runtime_state = type(
            "RuntimeState",
            (),
            {
                "_store": store,
                "_letterbox_params": [None, None],
                "_content_rect_px": None,
                "_inner_content_rect_px": None,
                "_inner_split_position": None,
                "_content_sr": 1.0,
                "_clip_overlays_to_content_rect": False,
                "_capture_circles": [],
                "_guide_sets": [],
            },
        )()
        self.overlay_coords = None
        self.gpu_params = None

    # widget geometry (the letterbox owner fits into these)
    def width(self):
        return WIDGET[0]

    def height(self):
        return WIDGET[1]

    def clear_feature_overlay_gpu(self):
        self.overlay_coords = None

    def set_overlay_coords(
        self, capture_center, capture_radius, overlay_centers, overlay_radius
    ):
        self.overlay_coords = (
            capture_center,
            capture_radius,
            tuple(overlay_centers),
            overlay_radius,
        )

    def set_feature_overlay_gpu_params(self, *args):
        self.gpu_params = args

    @property
    def glass_radius_px(self) -> float:
        assert self.overlay_coords is not None, "magnifier overlay was not applied"
        return float(self.overlay_coords[3])


def _apply_frame(store, img1, img2) -> tuple[float, object]:
    """One live apply: plan → letterbox → overlay conversion. Returns the
    widget-px glass radius and the plan that produced it."""
    plan = build_canvas_plan(store, img1, img2)
    assert plan.overlay_layout is not None, "magnifier layout must be built"
    canvas = _Canvas(store)
    # What set_pil_layers → upload_pil_images does with the applied pair.
    update_common_letterbox_geometry(canvas, plan.image1, plan.image2)
    apply_plan_runtime_overlays(canvas, plan)
    return canvas.glass_radius_px, plan


def test_glass_size_is_identical_for_preview_and_unified_frames():
    """The two frames a swap walks through must draw the same glass size."""
    store = _store(_img(PREVIEW_LEFT, (200, 40, 40)), _img(PREVIEW_RIGHT, (40, 200, 40)))
    preview_radius, preview_plan = _apply_frame(
        store, _img(PREVIEW_LEFT, (200, 40, 40)), _img(PREVIEW_RIGHT, (40, 200, 40))
    )
    unified_radius, unified_plan = _apply_frame(
        store, _img(UNIFIED, (200, 40, 40)), _img(UNIFIED, (40, 200, 40))
    )

    assert preview_plan.canvas_w > 0 and unified_plan.canvas_w > 0
    assert preview_radius == pytest.approx(unified_radius, rel=1e-6, abs=1e-6), (
        "the loupe glass must not depend on which tier is installed: preview-dim"
        f" frame draws {preview_radius:.3f}px, unified frame {unified_radius:.3f}px"
    )


def test_glass_size_is_identical_for_the_swapped_preview_frame():
    """Same pair in the opposite slot order: same canvas, same glass size."""
    store = _store(_img(PREVIEW_LEFT, (200, 40, 40)), _img(PREVIEW_RIGHT, (40, 200, 40)))
    forward_radius, _ = _apply_frame(
        store, _img(PREVIEW_LEFT, (200, 40, 40)), _img(PREVIEW_RIGHT, (40, 200, 40))
    )
    swapped_radius, swapped_plan = _apply_frame(
        store, _img(PREVIEW_RIGHT, (40, 200, 40)), _img(PREVIEW_LEFT, (200, 40, 40))
    )
    assert swapped_radius == pytest.approx(forward_radius, rel=1e-6, abs=1e-6), (
        "slot order must not change the loupe glass size: forward"
        f" {forward_radius:.3f}px vs swapped {swapped_radius:.3f}px on"
        f" canvas {swapped_plan.canvas_w}x{swapped_plan.canvas_h}"
    )


def test_same_size_pair_is_unchanged():
    """No regression for the common case: equal dims → glass identical to the
    pre-swap frame and to the swap (nothing to be invariant about)."""
    store = _store(_img(UNIFIED, (200, 40, 40)), _img(UNIFIED, (40, 200, 40)))
    before, _ = _apply_frame(store, _img(UNIFIED, (200, 40, 40)), _img(UNIFIED, (40, 200, 40)))
    after, _ = _apply_frame(store, _img(UNIFIED, (40, 200, 40)), _img(UNIFIED, (200, 40, 40)))
    assert before == pytest.approx(after, rel=1e-9, abs=1e-9)
    # size_relative still means "fraction of the comparison" (2:1 ratio kept):
    # canvas 1600x1600 fitted into 1000x800 -> 800x800, glass = 0.2/2 * 800.
    assert before == pytest.approx(0.1 * 800.0, rel=1e-6)


def test_one_sided_frame_falls_back_to_the_present_image():
    """Have-gate frame: only slot 1 present → the single image is the
    reference, and adding slot 2 of the same size does not move the glass."""
    only = _img(UNIFIED, (200, 40, 40))
    store = _store(only, None)
    one_side, _ = _apply_frame(store, only, None)
    two_sides, _ = _apply_frame(store, only, _img(UNIFIED, (40, 200, 40)))
    assert one_side == pytest.approx(two_sides, rel=1e-6, abs=1e-6)
