# Display image pipeline: unify → display cache → render

How a loaded image pair goes from disk to the "stored"/background texture
that the QRhi canvas draws, and the single-writer / single-picker rules that
keep display cache and presentation fallbacks consistent.

## The three roles

Every render frame deals with (up to) three different versions of each side
of the comparison:

1. **Full-resolution unified pair** — `image_state.image1/2`. Produced once
   per load by `_session_controller.py::_unify_images_worker_task` (resizes
   image1/2 to a common size via `resize_images_processor`, then wraps via
   `maybe_wrap_pixel_store()` as `TiledPixelStore` — see
   [tile-rendering-system.md](tile-rendering-system.md#gegl-style-pixel-storage)).
   Memmap-backed, never uploaded as a single whole-image GPU texture at full
   resolution.

2. **Display cache** — `render_cache.display_cache_image1/2`. A real PIL
   image downscaled to fit `render_config.display_resolution_limit`,
   used as the "stored" role: the whole-image background quad drawn at
   normal (non-hi-res) zoom. This is what `upload_pil_images(...,
   shader_letterbox=True)` uploads as a single GPU texture — no tiling, no
   viewport cropping.

3. **Hi-res "source" role** — `source_texture_ids` / `source_image1/2`. Used
   by the base canvas when `base_image.use_hires` is true (`shader_letterbox_mode
   and not diff_mode and zoom > 1.0 and source images ready`). The **magnifier**
   also samples this role whenever letterbox sources are ready (including at
   zoom ≤ 1), so `RhiCanvasRenderer.render` must `realize_tile_plan` for
   `source_*` whenever the magnifier GPU overlay is active — even if the base
   canvas is still drawing `stored_*`. Sources are tiled
   (`shared/rendering/tile_texture_service.py::TileTextureService`) and read
   from the memmap-backed full-res store; they are never eagerly uploaded as a
   single whole-image GPU texture.

## Single writer for the display cache

`render_cache.display_cache_image1/2` has exactly **one** writer:
`image_cache.py::create_preview_cache_async`, called every frame from
`render_flow.py::update_comparison_if_needed`. It:

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
never hand a `TiledPixelStore` to a renderer that expects a whole-image
texture/QPixmap. That's `shared/rendering/display_image_picker.py::pick_first_real`,
used by both call sites instead of two hand-rolled `or`-chains.

## Rules

- If you need a new place to read "the current display-ready image," call
  `pick_first_real`.
- If you need to change how/when the display cache gets (re)computed, change
  `create_preview_cache_async` — don't add a second writer.
- Do not put a full-resolution image into `display_cache_image*` — the
  "stored" role is a whole-image GPU texture, not a tile grid.
