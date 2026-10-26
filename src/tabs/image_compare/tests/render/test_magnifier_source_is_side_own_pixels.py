"""The magnifier's per-side source is THE SIDE'S OWN PIXELS, not the canvas tier.

Why this file exists (owner report, 2026-10-26): with a 2816x2304 left image and
a 768x576 right image the loupe over the right side was *mush*, while the same
loupe over the left side showed real structure — and zooming the canvas made the
right side blurrier. Measured with ``IMGSLI_TILE_DUMP=1`` on a leased instance:

    {"kind": "magnifier.grid_dims", "source_key": "source_0",
     "total_width": 2816, "total_height": 2304, ...}
    {"kind": "magnifier.grid_dims", "source_key": "source_1",
     "total_width": 2816, "total_height": 2304, ...}   # <- the 768x576 image!

Both sides sampled a grid registered at the *unified canvas* size, because
``image_state.image1/2`` hold the UNIFIED stores (``engine/store/pixel_ops/
unify.py`` resamples both sides to the common canvas) and the live presentation
hands those to the magnifier source role. The loupe therefore magnified an
already-upscaled copy of the small image: no real pixels left to show.

Existing coverage did not catch it: the source-key tests assert the keys become
RESIDENT (``is_resident("source_0", (0, 0))``) and never assert the grid SIZE,
and every loupe test injects its own ``TileTextureService`` with a hand-registered
grid (512x512 / 2048x2048) — so the production decision "which pixels does the
source role get" was never exercised.

Guarded here: the presentation's SOURCE role resolves to the side's own pixel
tier (the original store) while the DISPLAY role keeps the unified/display pick.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from PIL import Image

from engine.store.tiled_pixel_store import TiledPixelStore
from tabs.image_compare.canvas.presentation.live_presentation import (
    build_live_store_presentation,
)
from tabs.image_compare.pipeline.cache import _pixel_key

LEFT = (800, 600)   # unified canvas (max of both sides)
RIGHT_ORIGINAL = (200, 150)  # the small side's own pixels, pre-unify


def _tps(size: tuple[int, int], tmp_path, color=(90, 90, 90)) -> TiledPixelStore:
    return TiledPixelStore.from_pil(Image.new("RGB", size, color), tmp_dir=str(tmp_path))


def _store(tmp_path, *, both_unified: bool = True, with_pixel_cache: bool = True):
    """Store stand: image_state holds the UNIFIED pair (as after unify_pair),
    the pipeline cache still holds each side's ORIGINAL pixel tier by path."""
    left_unified = _tps(LEFT, tmp_path, (200, 40, 40))
    right_unified = _tps(LEFT, tmp_path, (40, 40, 200)) if both_unified else _tps(
        RIGHT_ORIGINAL, tmp_path, (40, 200, 40)
    )
    left_original = _tps(LEFT, tmp_path, (200, 40, 40))
    right_original = _tps(RIGHT_ORIGINAL, tmp_path, (40, 200, 40))

    paths = ("/gallery/left_big.png", "/gallery/right_small.png")
    document = SimpleNamespace(image1_path=paths[0], image2_path=paths[1])
    pipeline = SimpleNamespace(
        pixel=(
            {
                _pixel_key(paths[0], None, None): left_original,
                _pixel_key(paths[1], None, None): right_original,
            }
            if with_pixel_cache
            else {}
        ),
        preview={},
        unify={},
    )
    image_state = SimpleNamespace(image1=left_unified, image2=right_unified)
    store = SimpleNamespace(
        viewport=SimpleNamespace(
            session_data=SimpleNamespace(
                image_state=image_state,
                render_cache=SimpleNamespace(),
            ),
        ),
    )
    slots = {"document": document, "pipeline": pipeline}
    store.get_session_state_slot = lambda name: slots.get(name)
    return store, {
        "left_unified": left_unified,
        "right_unified": right_unified,
        "right_original": right_original,
    }


def test_source_role_is_the_side_own_pixels_not_the_unified_canvas(tmp_path):
    store, parts = _store(tmp_path)
    presentation = build_live_store_presentation(store)

    size = getattr(presentation.source_image2, "size", None)
    assert tuple(size) == RIGHT_ORIGINAL, (
        "the magnifier samples source_image2; it must be the side's own pixel "
        f"tier {RIGHT_ORIGINAL}, got {size} (the unified canvas tier means the "
        "loupe magnifies an upscaled copy: no real pixels to show)"
    )


def test_display_role_keeps_the_unified_pick(tmp_path):
    """The display role is the unify result (what the canvas paints) — this test
    only pins that the fix does not steal it for the magnifier's benefit."""
    store, parts = _store(tmp_path)
    presentation = build_live_store_presentation(store)
    assert presentation.display_image2 is not None
    assert tuple(getattr(presentation.display_image2, "size", ())) == LEFT


def test_source_role_image_prefers_own_pixels_and_ignores_previews(tmp_path):
    """The resolver the plan default and the presentation share.

    ``build_canvas_plan`` cannot be unit-called (it builds the whole live scene
    graph); its default is one call into this resolver, so the resolver IS the
    contract — the integration half is checked live: with the fix,
    ``realize.size`` reports ``src_w=768`` for ``source_1`` (was 2816) and
    ``magnifier.grid_dims`` reports 768x576.
    """
    from tabs.image_compare.canvas.presentation.source_tier import source_role_image

    store, parts = _store(tmp_path)
    assert source_role_image(store, 2, parts["right_unified"]) is parts["right_original"]
    # no cache entry -> the display image is the honest fallback
    empty, _ = _store(tmp_path, with_pixel_cache=False)
    assert source_role_image(empty, 2, parts["right_unified"]) is parts["right_unified"]
