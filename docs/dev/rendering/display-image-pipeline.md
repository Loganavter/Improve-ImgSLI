# Display image pipeline: unify → display cache → render

How a loaded image pair goes from disk to the "stored"/background texture
that both the QRhi canvas and the legacy `QLabel` renderer draw, why this
used to be spread across three independent implementations, and the rule
that keeps it from happening again.

## The three roles

Every render frame deals with (up to) three different versions of each side
of the comparison:

1. **Full-resolution unified pair** — `image_state.image1/2`. Produced once
   per load by `_session_controller.py::_unify_images_worker_task` (resizes
   image1/2 to a common size via `resize_images_processor`, then wraps
   anything over `PHASE3_LAZY_THRESHOLD_PX` as a `LazyPixelSource` — see
   [tile-rendering-system.md](tile-rendering-system.md#host-side-memory-bounding)).
   This can be a memmap-backed `LazyPixelSource`, never a whole-image GPU
   texture.

2. **Display cache** — `render_cache.display_cache_image1/2`. A real
   (non-lazy) PIL image downscaled to fit `render_config.display_resolution_limit`,
   used as the "stored" role: the whole-image background quad drawn at
   normal (non-hi-res) zoom. This is what `upload_pil_images(...,
   shader_letterbox=True)` uploads as a single GPU texture — no tiling, no
   viewport cropping.

3. **Hi-res "source" role** — `source_texture_ids` / `source_image1/2`. Used
   only when `base_image.use_hires` is true (`shader_letterbox_mode and not
   diff_mode and zoom > 1.0 and source images ready`). This role is allowed
   to be tiled (`shared/rendering/tile_texture_service.py::TileTextureService`)
   and is the only place a `LazyPixelSource` is meant to end up.

## Single writer for the display cache

`render_cache.display_cache_image1/2` has exactly **one** writer:
`image_cache.py::create_preview_cache_async`, called every frame from
`render_flow.py::update_comparison_if_needed` (for both the canvas and the
legacy `QLabel` path). It:

- short-circuits if the cache already matches `(image_uid(img1),
  image_uid(img2), limit)`,
- writes synchronously, unchanged, if `limit <= 0` or the image already fits,
- otherwise dispatches a background worker that downscales via
  `shared/image_processing/resize.py::downscale_pair_to_limit` and writes
  the result once it lands.

`_session_controller.py::_unify_images_worker_task` (session/unify layer)
does **not** touch `display_cache_image1/2` — it only produces
`image_state.image1/2`. When a fresh unify result or a
`unified_image_cache` hit lands (`loading.py::on_unified_images_ready` /
the cache-hit branch in `set_current_image`), it explicitly clears
`display_cache_image1/2` (and `last_display_cache_params`) rather than
writing a value into it, so the per-frame path always recomputes on its own
terms instead of two writers racing.

## Single picker for "what do we actually show"

Both `plan_builder.py::build_live_store_presentation` (canvas) and
`render_flow.py::update_comparison_if_needed`'s single-image-mode branch
need the same fallback chain — display cache, then scaled-for-display cache,
then the live unified image, then a preview/original fallback — and must
never hand a `LazyPixelSource` to a renderer that expects a whole-image
texture/QPixmap. That's `shared/rendering/display_image_picker.py::pick_first_real`,
used by both call sites instead of two hand-rolled `or`-chains.

## The bug this replaced

Before this refactor, both the unify worker *and* the per-frame path wrote
`display_cache_image1/2`, using different downscale math and different
invalidation timing. The unify worker's write raced against the per-frame
write; on `unified_image_cache` cache hits (re-selecting an already-loaded
pair) the write bypassed downscaling entirely and stuffed the full-resolution
image straight into `display_cache_image1`. For images above
`_LIVE_TILE_EXTENT` (8192px), that made `RhiResources.upload_source`
register a real NxM tile grid for the "stored" role — which is never
supposed to be tiled — and only the first resident tile rendered, appearing
as a small square instead of the full image.

**Rule going forward:** if you need a new place to read "the current
display-ready image," call `pick_first_real`. If you need to change how/when
the display cache gets (re)computed, change `create_preview_cache_async` —
don't add a second writer.
