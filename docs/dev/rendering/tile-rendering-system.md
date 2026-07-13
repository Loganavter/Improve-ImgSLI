# Tiled rendering system

How the QRhi renderer handles source images too large to live as a single
GPU texture. Written from memory of the implementation, not a line-by-line
source dump — treat file/line references as approximate, verify against code
before relying on exact names.

## Why tiling exists

A GPU texture has a practical size ceiling, and even below that ceiling,
uploading/holding a full 18000×18000px texture per side is wasteful when
only a fraction of it is ever on-screen at once (interactive pan/zoom on a
hi-res source). `canvas/rhi_renderer/resources.py` defines `_LIVE_TILE_EXTENT`
(8192px) as the threshold: any texture source wider or taller than that gets
split into an N×M grid of tiles instead of one whole-image texture, and only
the tiles currently intersecting the viewport are actually resident on the
GPU.

Two roles ever get texture-uploaded (see
[display-image-pipeline.md](display-image-pipeline.md) for the full role
breakdown):

- **"stored"** (`stored_0`/`stored_1`) — the default, non-zoomed background
  quad. This is *supposed* to always end up a 1×1 grid, because
  `display_cache_image1/2` is deliberately downscaled below
  `_LIVE_TILE_EXTENT` before it ever reaches `upload_pil_images`. If a 1×1
  assumption breaks here, tiling machinery still "works" but produces the
  wrong visual result — see that doc's "bug this replaced" section for what
  happens when it doesn't.
- **"source"** (`source_0`/`source_1`) — the hi-res role, only bound when
  `base_image.use_hires` is true (`shader_letterbox_mode`, not diff mode,
  `zoom_level > 1.0`, source images ready). This is the role genuinely
  expected to be tiled for large images.

## `TileTextureService` — grid bookkeeping

`shared/rendering/tile_texture_service.py`. One `TileTextureService` instance
owns a dict of `source_id -> grid` for every texture key currently in use.

- `register_source(source_id, image_size)` — the only place that creates or
  updates a source's grid. Called exclusively from
  `RhiResources.upload_source`, which itself is only reachable through the
  `queue_texture_upload` → `apply_pending_uploads` path. If a key never goes
  through that path, its grid is never (re-)registered and `grid_for(key)`
  returns `None` or a stale grid — this used to be a real footgun for lazy
  sources, since `upload_pil_images` intentionally skips queuing an upload
  for a `LazyPixelSource` in the "stored" role.
- A grid smaller than `_LIVE_TILE_EXTENT` on both axes registers as a
  trivial 1×1 grid — the common case, treated as "not tiled" everywhere
  downstream (`grid.rows == 1 and grid.columns == 1` is the standard
  short-circuit check).
- `grid_for(key)` — read-only lookup, `None` if never registered.
- `tile_key(source_id, row, col)` — builds the composite key used for the
  actual per-tile GPU texture cache entry, distinct from the bare
  `source_id`.
- `visible_tiles(source_id, visible_rect)` — given a rect in the grid's own
  pixel space, returns the set of `(row, col)` indices whose region
  intersects it. This is the single computation that both the residency pass
  (`RhiResources.realize_tile_plan`) and the draw-plan pass
  (`draw_plan.py::_visible_tile_pairs`) rely on, so what's uploaded and what's
  drawn are guaranteed to agree.
- `grid.iter_regions()` — yields `(row, col, region)` for every cell, where
  `region` has pixel-space `left/top/right/bottom`.

## Apron padding

`texture_parts/tile_geometry.py::_apron_rect` / `_TILE_APRON_PX`. Each tile's
uploaded pixel region is padded by a few pixels beyond its "logical" grid
cell before cropping, so bilinear sampling near a tile's edge doesn't sample
outside that tile's own texture (which would either clamp to edge color or
wrap, producing visible seams at tile boundaries). The rect fractions passed
to the shader (`tileRect1`/`tileRect2` uniforms) are computed from this
apron-padded region, not the raw grid cell — draw code and residency code
must agree on this or you get texture/geometry mismatch (exactly the kind of
bug the tiled system is fragile to if one side changes independently).

## Residency: `RhiResources.realize_tile_plan`

Runs once per frame (or whenever geometry/viewport changes trigger it).
For each `(texture_key, letterbox)` pair that has a real (non-1×1) grid:

1. Determine which tiles are currently visible (same `visible_tiles` call the
   draw plan will use).
2. Crop and upload only those tiles. If the underlying PIL image is a
   `LazyPixelSource` (memmap-backed, over the lazy-storage threshold — see
   "Host-side memory bounding" below), tiles are cropped directly from the
   memmap via `.crop()` — the whole image is never materialized in memory
   just to cut tiles out of it.
3. Evict tiles that are no longer in the protected (visible) set, so GPU
   memory for a given source stays bounded to roughly "what's on screen"
   rather than growing to the full grid over a pan session.

## Draw plan: `rhi_renderer/draw_plan.py`

`build_draw_plan()` produces a flat list of `DrawItem`s, one per actual draw
call the frame needs. The shader binds exactly one texture per side (image1,
image2, optionally diff) per draw call, so if image1 has 2 visible tiles and
image2 has 3, the draw plan is their **cross product** — up to 6 draw calls,
each pairing one image1 tile with one image2 tile, with `tileRect1`/`rect2`
uniforms telling the shader which sub-region of each bound texture
corresponds to that draw call's on-screen geometry.

`_visible_tile_pairs()` does the per-side visible-tile lookup (delegating to
`TileTextureService.visible_tiles`, using the same viewport-rect computation
`_visible_side_image_rect` that residency uses) and returns the cross
product. A 1×1 (untiled) side just contributes its single whole-image key +
full-rect entry, so the untiled case is really this same code path with a
degenerate one-element list on each side.

### Diff texture tiling

The diff overlay only has a single sampler slot in the shader and is always
computed from image1's full-resolution pixels, so a draw call reuses
`tileRect1` to sample it — `_resolve_diff_tile_key()` picks whichever single
diff tile best overlaps that draw call's `rect1` window (`best-pixel-overlap`
by area). This is exact whenever the diff grid and image1's live grid match
(the steady-state case). It only degrades to an approximate pick during
interactive pan/zoom, when image1's *display* texture is transiently
downscaled for smoothing and simultaneously both it and the diff exceed a
single tile — cosmetic-only, not a correctness bug.

## Host-side memory bounding

GPU tile residency (above) only bounds *GPU* memory. Two complementary
mechanisms bound *host* RAM for the same large-image path — both grew out of
an OOM investigation (18000×18000px sources driving the process to a
13GB+ RSS peak and swap-thrashing) but are permanent architecture, not a
one-off fix:

- **`_texture_upload_cache` LRU budget** (`texture_parts/upload_queue.py`,
  `canvas/state.py`) — the host-side QImage cache behind texture uploads
  (`stored_0/1`, `source_0/1`, `diff`) is an `OrderedDict` with a byte budget
  (`_HOST_TEXTURE_CACHE_BUDGET_BYTES`, 3 GiB) and real LRU-by-recent-use
  (`touch_texture_upload_cache()` on every read hit). `RhiResources.realize_tile_plan`
  calls `evict_texture_upload_cache_over_budget(widget, protected, budget_bytes)`
  once per frame with `protected` = whichever texture keys this frame
  actually reads — so the on-screen role can never be evicted mid-frame, only
  the currently-unused role (e.g. `source_N` while not in hi-res mode) ages
  out. Eviction is a memory/recompute tradeoff, never a correctness one: a
  cache miss in `realize_tile_plan` re-decodes from the retained PIL source
  (`_pil_image_for_texture_key`) and repopulates the cache before cropping.
  Tests: `src/tabs/image_compare/tests/render/test_host_texture_cache_budget.py`.

- **`LazyPixelSource`** (`src/shared/image_processing/lazy_pixel_source.py`)
  — for source images over `AppConstants.PHASE3_LAZY_THRESHOLD_PX` (16384px,
  `2 * _LIVE_TILE_EXTENT`), the decoded RGBA8 buffer is spilled to a
  memory-mapped temp file instead of held as anonymous heap for the
  document's lifetime, so it's OS-page-cache backed and reclaimable under
  memory pressure instead of forcing swap. It duck-types `.size`/`.width`/
  `.height`/`.mode`/`.info`/`.crop()` so existing readers need minimal
  branching; `.crop(box)` returns a small materialized PIL Image (what
  `realize_tile_plan` uses per-tile, never materializing the whole image),
  while `.to_pil()` returns a full one-shot materialized copy for the few
  consumers that need one regardless of size (SSIM diff, export/save — both
  inherently touch every pixel anyway). `maybe_wrap_for_lazy_storage()` /
  `close_if_lazy()` are the threshold-gate and cleanup helpers, called from
  `_session_controller.py`'s `_update_image_slot` and `use_cases/loading.py`'s
  `handle_full_image_loaded`. Tests:
  `src/tabs/image_compare/tests/render/test_lazy_pixel_source.py`.

The one remaining permanent resident this doesn't (and can't cheaply) bound
is `document.full_res_image1/2` itself — one full-res PIL/`LazyPixelSource`
per side, kept for the document's lifetime because consumers (magnifier pan,
the tile re-decode fallback above) need repeated random-offset access, and
some sources (clipboard paste, video-editor extracted frames) have no file
path to re-decode from. Reducing that further would mean true on-disk
streaming decode (no current codec dependency supports it for PNG/JPEG/WebP)
— not attempted, treated as working-as-intended.

## Summary of the invariant

Registration (`register_source`), residency (`realize_tile_plan`), and the
draw plan (`_visible_tile_pairs`) all go through the same
`TileTextureService` grid and the same `visible_tiles`/viewport-rect
computation. As long as a texture key's grid is registered before either
residency or the draw plan run against it, "what's GPU-resident" and "what
the draw plan expects to sample" can't silently diverge — that agreement is
the entire point of centralizing grid state in `TileTextureService` instead
of letting residency and drawing each recompute it independently.
