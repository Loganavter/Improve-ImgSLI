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
- **"source"** (`source_0`/`source_1`) — the hi-res role. The base canvas binds
  it when `base_image.use_hires` is true (`shader_letterbox_mode`, not diff
  mode, `zoom_level > 1.0`, source images ready). The magnifier also samples
  this role whenever letterbox sources are ready (including at zoom ≤ 1), so
  `RhiCanvasRenderer` realizes `source_*` tiles whenever the magnifier GPU
  overlay is active even if the canvas is still on `stored_*`. This is the
  role genuinely expected to be tiled for large images.

## `TileTextureService` — grid bookkeeping

`shared/rendering/tile_texture_service.py`. One `TileTextureService` instance
owns a dict of `source_id -> grid` for every texture key currently in use.

- `register_source(source_id, image_size)` — the only place that creates or
  updates a source's grid. Called exclusively from
  `RhiResources.upload_source`, which itself is only reachable through the
  `queue_texture_upload` → `apply_pending_uploads` path. If a key never goes
  through that path, its grid is never (re-)registered and `grid_for(key)`
  returns `None` or a stale grid — a footgun for lazy sources, since
  `upload_pil_images` intentionally skips queuing an upload
  for a `TiledPixelStore` in the "stored" role (display cache is downscaled PIL).
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
2. Crop and upload only those tiles. Underlying full-res pixels live in
   `TiledPixelStore` (memmap-backed — see "GEGL-style pixel storage" below);
   tiles are cropped via `.crop()` — the whole image is never materialized
   in memory just to cut tiles out of it.
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

## GEGL-style pixel storage

`TiledPixelStore` (`shared/image_processing/tiled_pixel_store.py`) is the
single full-res pixel backend for all canvas tabs. Every decoded image is
spilled to a memmap RGBA8 file in host tiles of
`AppConstants.PIXEL_TILE_SIZE` (512px). There is no small-image fast path at
the public API — `maybe_wrap_pixel_store()` always wraps.

Shared cross-tab render helpers (2026-07-15):

- `shared/rendering/host_texture_cache.py` — LRU QImage upload cache
- `shared/rendering/export_tiling.py` — `TiledFramebufferExporter`,
  `iter_export_tile_rects`
- `shared/rendering/tile_geometry.py` — `crop_apron_tile`,
  `viewport_zoom_offset_for_tile`

## PixelSource contract and tier rules

Two explicit tiers — cross-tier work goes through `shared/image_processing/pixel_ops/`:

| Tier | Type | Used for |
|------|------|----------|
| Full-res | `TiledPixelStore` | `document.full_res_image*`, unified pair, GPU source role |
| Display | `PIL.Image` | preview, `display_cache_image*`, scaled display, thumbnails |

### Preview-at-load tier

Progressive load (`load_preview_image`, ≤1024 px long edge) writes
`document.preview_image*` as **`PIL.Image` only**. Workers pass
`is_preview=True` and must not call `maybe_wrap_pixel_store` on that path;
full-res decode is a separate async step into `full_res_image*`
(`TiledPixelStore`). Contract: `tests/contracts/test_preview_tier_contract.py`.

Replacing PIL preview with `QImage` decode is tracked in
[TODO.md](../TODO.md) (P2, design needed) — not required for tier correctness.

### Host vs GPU tile granularity

Two tile sizes are **intentional**, not drift:

| Layer | Constant | Typical size | Role |
|-------|----------|--------------|------|
| Host storage / CPU ops | `AppConstants.PIXEL_TILE_SIZE` | 512 (square) | memmap `TiledPixelStore`, crop/read_tile, pixel_ops blocks |
| GPU residency | `_LIVE_TILE_EXTENT` / `SLOT_LIVE_TILE_EXTENT` | 8192 | texture upload grid, draw-plan cross product, VRAM budget |

**GEGL precedent:** storage uses small tiles (env default `128×64`; commit
history moved between `128×128`, `512×64`, etc. via `GEGL_TILE_SIZE`), while
the operation graph evaluates **larger ROIs** — OpenCL code batches regions
like 2048×4096 because kernel launch overhead dominates at storage-tile size.
Storage granularity controls RAM, swap, tile-cache, and mipmap damage; compute
granularity controls throughput.

Improve-ImgSLI follows the same split: host 512 keeps CPU crops bounded;
GPU 8192 keeps draw/residency manageable. Requirement: GPU extent should
remain a whole multiple of host tile size (8192 = 16×512). Formal shared
constants + contract tests: [TODO.md](../TODO.md) (P2).


- **`PixelSource`** protocol: [`pixel_source.py`](../../src/shared/image_processing/pixel_source.py)
- **`StoreLease`**: [`store_lease.py`](../../src/shared/image_processing/store_lease.py) — workers capture `(store, generation)` and bail if the store was closed
- **Tile-native ops**: `pixel_ops/downscale.py` (display cache), `pixel_ops/unify.py` (load unify), `shared/analysis/ssim_source.py` and `shared/analysis/diff_source.py` (SSIM/highlight/grayscale/edges without full RGB materialize)
- **`materialize_full()` / `to_real_pil_copy()`** — escape hatches only; AST contract [`tests/contracts/test_pixel_source_tiers.py`](../../tests/contracts/test_pixel_source_tiers.py) keeps call sites confined

### Audit: former hot spots (2026-07)

| Call site | Tier rule today |
|-----------|-----------------|
| `image_cache.py` display worker | `pixel_ops/downscale` only |
| `_session_controller` unify worker | `pixel_ops/unify` + `StoreLease` |
| `cached_diff.py` / `background_layers.py` | `ssim_source` / `diff_source` tile-fed |
| `metrics.py` | display cache first; else bounded downscale |
| `image_export/context_builder.py` | `unify_pair` + GPU snapshot primary |
| `qimage_from_pixel_source` whole store | host-tile stitch, no `materialize_full` |
| magnifier `diff_cache.py` worker | `StoreLease` on async SSIM |
| video/export snapshot prepare | unpadded `TiledPixelStore` + `CanvasGeometry` / `overlay_clip_rect`; GPU `shader_letterbox` (no PIL letterbox/pad bake) |

## Host-side memory bounding

GPU tile residency (above) only bounds *GPU* memory. Two complementary
mechanisms bound *host* RAM for the same large-image path — both grew out of
an OOM investigation (18000×18000px sources driving the process to a
13GB+ RSS peak and swap-thrashing) but are permanent architecture, not a
one-off fix:

- **`HostTextureUploadCache`** (`shared/rendering/host_texture_cache.py`) —
  generalized from image_compare's `upload_queue.py`; image_compare keeps a
  thin facade keyed on its five texture roles. Tests:
  `tests/render/test_host_texture_cache.py` and
  `src/tabs/image_compare/tests/render/test_host_texture_cache_budget.py`.

- **`TiledPixelStore`** — see [GEGL-style pixel storage](#gegl-style-pixel-storage).
  `.crop(box)` / `read_tile(row, col)` return small materialized regions for
  GPU residency; `.materialize_full()` / `.to_pil()` are explicit escape
  hatches for SSIM diff and export/save. `close_pixel_store()` closes stores.
  Tests: `tests/render/test_tiled_pixel_store.py`.

The one remaining permanent resident this doesn't (and can't cheaply) bound
is `document.full_res_image1/2` itself — one full-res `TiledPixelStore`
per side, kept for the document's lifetime because consumers (magnifier pan,
the tile re-decode fallback above) need repeated random-offset access, and
some sources (clipboard paste, video-editor extracted frames) have no file
path to re-decode from.

**Strip spill on load (plan A):** `TiledPixelStore.from_pil` /
`from_path` write RGBA into the memmap in `PIXEL_TILE_SIZE` strips instead of
`memmap[:] = np.asarray(full)`. Peak host RAM during spill is one decode
buffer plus a strip, not a second full `HxWx4` copy. File loads in
image_compare / video export / multi_compare go through `from_path` (with
optional `auto_crop` via a bounded downscale probe). This is **not** codec
ROI streaming — JPEG/PNG/WebP still decompress the whole frame once; only the
second contiguous copy is avoided. Raising
`MAX_SUPPORTED_IMAGE_DIMENSION` (65536) still waits on a real streaming
decode path.

## Summary of the invariant

Registration (`register_source`), residency (`realize_tile_plan`), and the
draw plan (`_visible_tile_pairs`) all go through the same
`TileTextureService` grid and the same `visible_tiles`/viewport-rect
computation. As long as a texture key's grid is registered before either
residency or the draw plan run against it, "what's GPU-resident" and "what
the draw plan expects to sample" can't silently diverge — that agreement is
the entire point of centralizing grid state in `TileTextureService` instead
of letting residency and drawing each recompute it independently.
