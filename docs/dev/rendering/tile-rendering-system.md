# Tiled rendering system

How the QRhi renderer handles source images too large to live as a single
GPU texture. Written from memory of the implementation, not a line-by-line
source dump — treat file/line references as approximate, verify against code
before relying on exact names.

## Why tiling exists

A GPU texture has a practical size ceiling, and even below that ceiling,
uploading/holding a full 18000×18000px texture per side is wasteful when
only a fraction of it is ever on-screen at once (interactive pan/zoom on a
hi-res source). `shared/rendering/tile_constants.py` defines
`LIVE_TILE_EXTENT` (512px — see
`tile-array-atlas-plan.md` Phase 3 (private, `improve-imgsli-internal-docs`, `docs/legacy/rendering/`) for why it's
no longer 8192) as the threshold: any texture source wider or taller than
that gets split into an N×M grid of tiles instead of one whole-image
texture, and only the tiles currently intersecting the viewport are
actually resident on the GPU.

Two roles ever get texture-uploaded (see
[display-image-pipeline.md](display-image-pipeline.md) for the full role
breakdown):

- **"stored"** (`stored_0`/`stored_1`) — the default, non-zoomed background
  quad. Its base grid can be a large `TiledPixelStore`; at whole-image scale
  the per-frame LOD pick (below) resolves it to a coarse pyramid level whose
  grid is 1×1, keeping the common case untiled without a separate downscale
  step.
- **"source"** (`source_0`/`source_1`) — the hi-res role. The base canvas binds
  it when `base_image.use_hires` is true (`shader_letterbox_mode`, not diff
  mode, `zoom_level > 1.0`, source images ready). The magnifier also samples
  this role whenever letterbox sources are ready (including at zoom ≤ 1), so
  `RhiCanvasRenderer` realizes `source_*` tiles whenever the magnifier GPU
  overlay is active even if the canvas is still on `stored_*`. This is the
  role genuinely expected to be tiled for large images.

  This extra realize call passes `capture_uv_rect` (the union of the
  overlay's active `OverlaySlot.uv_rect`/`uv_rect2`, a zoom/pan-invariant
  fraction of the full source image) instead of `viewport_zoom`/
  `viewport_offset`. Passing the canvas's own viewport at canvas zoom ≤ 1
  made `_visible_side_image_rect` treat the *entire* image as visible in
  full-resolution pixel space — far more tiles than one frame's upload
  budget can realize, so the small area the magnifier actually points at
  could stay non-resident indefinitely (visible as black/empty tiles in the
  magnifier). `capture_uv_rect` bypasses letterbox mapping entirely (the
  overlay's uv_rect is already in the target texture's own native 0..1
  space) and scopes residency to just the capture window.

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
  (`TileResidencyRealizer.realize_tile_plan` (owned by `RhiResources` as `.residency`)) and the draw-plan pass
  (`draw_plan.py::_visible_tile_pairs`) rely on, so what's uploaded and what's
  drawn are guaranteed to agree.
- `grid.iter_regions()` — yields `(row, col, region)` for every cell, where
  `region` has pixel-space `left/top/right/bottom`.

## Mipmap pyramid and LOD selection

`shared/image_processing/pyramid_pixel_store.py::PyramidPixelStore` wraps a
unified base `TiledPixelStore` with derived levels (2×2 box-filter halving,
finest-first, down to `min(w, h) <= COARSEST_MIN_DIM` = 1024px). Each level
is its own `TiledPixelStore` (own memmap spill), so tile addressing, leases
and apron handling are identical at every level. `pyramid_registry.py`
(`pyramid_for(source)`) maps a base store to its built pyramid, if any;
sides without one (plain PIL, preview tier, pyramid not yet built or
invalidated) fall through untouched.

`shared/rendering/lod.py::select_level(dest_scale, level_count)` is the
single pure function both the live canvas and snapshot/export call to pick
a level — see [rendering-model.md](rendering-model.md) for the parity
requirement. `draw_plan.py` substitutes each side's texture key with a
`LevelKey(base, level)` before building tile pairs; `resources.py` resolves
a `LevelKey` back to the level's `TiledPixelStore` at realize time, clamping
to whatever level is actually published so far (levels build and publish
progressively). Level 0 keeps the bare base key, so the no-pyramid path is
byte-identical.

## Apron padding

`shared/rendering/tile_geometry.py::_apron_rect` / `_TILE_APRON_PX`. Each tile's
uploaded pixel region is padded by a few pixels beyond its "logical" grid
cell before cropping, so bilinear sampling near a tile's edge doesn't sample
outside that tile's own texture (which would either clamp to edge color or
wrap, producing visible seams at tile boundaries). The rect fractions passed
to the shader (`tileRect1`/`tileRect2` uniforms) are computed from this
apron-padded region, not the raw grid cell — draw code and residency code
must agree on this or you get texture/geometry mismatch (exactly the kind of
bug the tiled system is fragile to if one side changes independently).

## Residency: `TileResidencyRealizer.realize_tile_plan`

Owned by `RhiResources` as `self.residency`; callers invoke it as
`resources.residency.realize_tile_plan(...)`.

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

## Fallback-LOD: preserving previous content across a residency gap

Both tabs draw a *previous* LOD/pyramid level's still-resident tiles
underneath a newly-selected level while that new level's own tiles are
still trickling in via the budgeted upload loop above, so a LOD change
(zoom crossing a pyramid-level boundary, or a slot's source swapping to a
different size/resolution) never shows a blank hole mid-transition. This is
a **cross-frame bookkeeping problem**, not a residency or draw-plan one: it
needs to remember, per side/slot, "what key was last known to be fully
drawable" and keep serving that key's tiles until the new key catches up.

**The three pieces of state**, owned by the caller (`RhiCanvasRenderer` in
image_compare, `BaseImagesPass` in multi_compare — *not* by
`TileResidencyRealizerBase`/`residency.py`, which holds no cross-frame LOD
state at all, only fixed config; see
`renderer-unification-plan.md` Phase 3 (private, `improve-imgsli-internal-docs`, `docs/legacy/rendering/`)):

- `last_good_key` (per side/slot) — the key currently considered safe to
  promote to as "the" current content once its own tiles are complete.
- `key_more_pending` (per key) — whether that key's own upload still has
  outstanding tiles this frame, recomputed fresh every `realize()` call from
  actual residency state, never carried stale across frames.
- The fallback draw itself: when the *new* key's tiles aren't complete yet,
  the old (`last_good_key`) key's tiles are drawn first, then the new key's
  tiles on top, so the new key's partial content occludes only the region
  it's actually able to cover.

### The critical invariant: coverage must be computed from resident tiles only

The fallback tile set shrinks over time via a coverage check
(`shared/rendering/tile_coverage.py::covered_fraction`,
`FALLBACK_COVERAGE_THRESHOLD = 0.98`, point-sampled 9×9 — see that module's
docstring for why point-sampling instead of an area sum: overlapping/
duplicate rects in the "current" list, which arise by design here, made an
area sum overcount and falsely read as 100% covered) — a fallback tile is
dropped once the *current* key's own tiles already cover ~all of its
footprint, so old and new content don't visibly overlap for longer than
necessary.

**Both tabs got this wrong the same way, independently, at different
times**: the tile list fed into that coverage check as "what the current
key already covers" was the *geometrically visible* target set
(`build_array_draw_plan`/`build_slot_array_tiles` — every tile the viewport
wants, regardless of whether the residency pass has actually uploaded it
yet), not the *actually-resident* subset. A freshly-registered key's grid
is visible-but-empty the instant it's registered — every tile in it has a
GPU-slot lookup that returns `None` (see `TileTextureService.slot_for`)
until the budgeted upload loop lands it, over several frames for anything
past a couple tiles. Feeding that whole geometrically-visible list into the
coverage check made a large, mostly-empty new grid appear to "fully cover"
the screen on the very frame it was registered, so **every** fallback tile
got dropped immediately — the previous, fully-drawable content vanished for
several frames before the new key had uploaded anything to replace it,
i.e. exactly the blank-hole flash the whole mechanism exists to prevent.

- **multi_compare** (`scene/passes/base_images.py::_prepare_array_plan`):
  found and fixed 2026-07-30, in two passes. First pass filtered only the
  list fed to the coverage check itself. Second pass (same day, on review)
  filtered `current_tiles` to
  `tile_service.slot_for(key, tile.index) is not None` right where it's
  built from `build_slot_array_tiles`, so every downstream use — the
  promotion check, `tiles_for_key`, and the coverage denominator — reads
  the same residency-filtered list, matching image_compare's invariant
  below instead of only patching the one call site that had a proven
  symptom. The fallback side (`old_key`'s tiles) got the same treatment.
  This was the actual root cause of the original multi-session
  "zoom/pyramid-cascade corruption" investigation (half-flipped/
  overlapping/translucent tiles), not any of the earlier hypotheses tried
  against it — see `docs/dev/KNOWN_BUGS.md` "multi_compare: fallback-LOD
  coverage computed from non-resident tiles" for the full incident
  writeup.
- **image_compare** (`rhi_renderer/draw_plan.py::build_array_draw_plan`):
  checked, **does not have this bug**. Its pairing loop calls
  `tile_service.slot_for(src, idx)` for both sides and `continue`s past any
  index with no slot yet, so `current_array_plan` — the list handed to
  `drop_covered_fallback_items` — can never contain a non-resident item in
  the first place; there's no separate filter step to forget because the
  filtering is inherent to how the list gets built. (An earlier version of
  this investigation, before the code was re-read carefully, mistook
  `_array_side_tiles` — a genuinely unfiltered *intermediate* helper,
  analogous to multi_compare's `build_slot_array_tiles` — for what actually
  reaches the coverage check; it isn't, `build_array_draw_plan`'s own
  pairing loop filters before anything is appended to the list it
  returns.) multi_compare's fix above brings it in line with this same
  invariant, closing the divergence noted in
  `renderer-unification-plan.md` Phase 4 (private, `improve-imgsli-internal-docs`, `docs/legacy/rendering/`).

**Rule going forward**: any "is this old content already replaced" coverage
check in this codebase must be computed against `tile_service.slot_for(...)
is not None` (or equivalent actual-residency check), never against a
draw-plan's or geometry pass's target/visible tile list. The two are only
equal in the (common, easy-to-test-against-by-accident) steady state where
nothing is mid-upload — exactly the case that hides this bug until a fresh,
large, or otherwise slow-to-fill grid is involved.

### Content swaps are atomic; LOD churn is progressive

A LOD/pyramid-level churn (zoom crossing a level boundary on the *same*
source) gets the progressive reveal above — the coarser content stays
visible and the finer level's tiles replace it region by region, which is
the intended behavior. A genuine *content replacement* (preview→store flip,
a same-slot image swap, a source-role switch) must not: the user sees the
new content appear tile-by-tile over several frames as a patchwork mix of
old and new regions. ``resolve_fallback_lod``'s ``atomic=True`` mode draws
*only* the fallback baseline (the old content) until the new content's
current-view tiles are all resident, then flips the whole draw plan over in
one frame. The caller (``RhiCanvasRenderer._resolve_fallback_plan`` in
image_compare; the fixed-pair render tab is the only ``atomic`` caller
today) identifies a content swap by either of two signals:

1. A rekeyed old-content marker in the fallback baseline —
   ``("_prev_content", ...)`` (eager whole-image/diff-role path,
   ``residency.rekey_stale_content``) or ``("_content_stash", ...)`` (lazy
   TiledPixelStore path, ``residency._rekey_or_restore``). The marker
   persists in the caller's ``_last_good_*`` state for the whole
   transition, so no extra state is needed — the marker check must
   recognize *both* forms (a ``_prev_content``-only check left the lazy
   path in progressive mode).
2. A source identity change (``image_uid`` of the live sources differs from
   the last committed set). The preview→store flip re-registers the store
   under a fresh ``LevelKey`` and rekeys nothing, so its baseline (the old
   bare slot keys) carries no marker; the source-identity change is the
   only signal. It is a one-frame fact and must be persisted
   (``_content_swap_active``) until promotion.

Atomic mode also degrades gracefully: if the old-content fallback plan is
empty (the old content was fully evicted or never resident), the partial new
content is drawn rather than a blank frame.

### Non-idempotent upload under duplicate same-frame calls (multi_compare-specific)

A second, narrower bug in the same mechanism: `BaseImagesPass._upload_slot`
can be invoked twice in one frame for the identical `(sid, source)` pair —
`pending_uploads` is a plain list that `queue_upload()` appends to, and
`canvas_widget.py` can call it more than once for the same slot before the
next `apply_pending_texture_ops()` flush. This duplicate call is a
pre-existing, previously-harmless quirk (visible as duplicated `[slot-swap]`
log lines in every capture from this investigation) that only became
destructive once `_upload_slot` grew logic to rekey a slot's *previous*
grid to a fallback key before registering the new one (so
`last_good_key`/the mechanism above has something real to fall back to
across a source swap, not just across a LOD-level change): the first call
correctly rekeys the genuine old grid; without a guard, the second call
would see the fresh, still-empty grid the first call just registered,
mistake it for "old content worth preserving", and rekey *that* over the
real fallback — discarding the actual previous content the mechanism exists
to protect. Fixed with an early-return guard at the top of `_upload_slot`
(`if self.slot_pixel_sources.get(sid) is source: return`), making the
function idempotent under a duplicate call regardless of what the rekey
logic below it does.

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
| Display | `PIL.Image` | preview tier, `downscale_pair_to_limit` outputs (metrics, export sizing), thumbnails |

### Preview-at-load tier

Progressive load (`load_preview_image`, ≤1024 px long edge) decodes straight
to **`QImage`** (`QImageReader` + `setScaledSize` for the bounded preview,
`Format_RGBA8888`; PIL is only a fallback for formats `QImageReader` can't
decode — JXL via imagecodecs, unknown formats) and writes
`document.preview_image*` as `QImage`. Workers pass `is_preview=True` and
must not call `maybe_wrap_pixel_store` on that path; full-res decode is a
separate async step into `full_res_image*` (`TiledPixelStore`). Contract:
`src/tabs/image_compare/tests/contracts/test_preview_tier_contract.py`.

Auto-crop on the QImage path probes the crop box via a temporary PIL
in-memory view (`get_auto_crop_box`) without materializing a full-res PIL
image.

### Host vs GPU tile granularity

Two tile sizes are **intentional**, not drift, and now formalized in one
shared module: `shared/rendering/tile_constants.py` (`PIXEL_TILE_SIZE`,
`LIVE_TILE_EXTENT`, `DEFAULT_TILE_EXTENT`, `TILE_APRON_PX`,
`TILE_RESIDENCY_MARGIN`).

| Layer | Constant | Typical size | Role |
|-------|----------|--------------|------|
| Host storage / CPU ops | `PIXEL_TILE_SIZE` | 512 (square) | memmap `TiledPixelStore`, crop/read_tile, pixel_ops blocks |
| GPU residency | `LIVE_TILE_EXTENT` | 512 | texture upload grid, draw-plan cross product, VRAM budget |

**GEGL precedent:** storage uses small tiles (env default `128×64`; commit
history moved between `128×128`, `512×64`, etc. via `GEGL_TILE_SIZE`), while
the operation graph evaluates **larger ROIs** — OpenCL code batches regions
like 2048×4096 because kernel launch overhead dominates at storage-tile size.
Storage granularity controls RAM, swap, tile-cache, and mipmap damage; compute
granularity controls throughput.

Improve-ImgSLI follows the same split: host 512 keeps CPU crops bounded;
GPU 512 (since `tile-array-atlas-plan.md` Phase 3 (private, `improve-imgsli-internal-docs`, `docs/legacy/rendering/`);
8192 historically, see Part B below) keeps draw/residency manageable.
`AppConstants.PIXEL_TILE_SIZE`
still exists in `core/constants.py` for import-direction reasons (core must
not import `shared.rendering`) and is pinned equal to
`tile_constants.PIXEL_TILE_SIZE` by `tests/contracts/test_tile_constants.py`,
which also asserts `LIVE_TILE_EXTENT % PIXEL_TILE_SIZE == 0`.


- **Pixel sources**: `TiledPixelStore` and QImage-backed sources are normalized through [`tiled_pixel_store.py`](../../../src/shared/image_processing/tiled_pixel_store.py) (`qimage_from_pixel_source`, `pixel_source_size`)
- **`StoreLease`**: [`store_lease.py`](../../../src/shared/image_processing/store_lease.py) — workers capture `(store, generation)` and bail if the store was closed
- **Tile-native ops**: `pixel_ops/downscale.py` (`downscale_pair_to_limit` for metrics/export sizing), `pixel_ops/unify.py` (load unify), `shared/analysis/ssim_source.py` and `shared/analysis/diff_source.py` (SSIM/highlight/grayscale/edges without full RGB materialize)
- **`materialize_full()` / `to_real_pil_copy()`** — escape hatches only; AST contract [`tests/contracts/test_pixel_source_tiers.py`](../../../tests/contracts/test_pixel_source_tiers.py) keeps call sites confined

### Audit: former hot spots (2026-07)

| Call site | Tier rule today |
|-----------|-----------------|
| `_session_controller` unify worker | `pixel_ops/unify` + `StoreLease`; also starts the pyramid build |
| `cached_diff.py` / `background_layers.py` | `ssim_source` / `diff_source` tile-fed |
| `metrics.py` | bounded `downscale_pair_to_limit` (4096px, `allow_materialize=True`) |
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
  GPU residency; `.materialize_full()` (the sole full-frame escape hatch,
  confined by `tests/contracts/test_pixel_source_tiers.py`) serves SSIM
  diff and export/save. `close_pixel_store()` closes stores.
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
second contiguous copy is avoided.

**True ROI streaming (plan B, 2026-07):** implemented via `pyvips`, which is
a **hard dependency** in every packaging target (`pyvips[binary]` in
`requirements-gui.txt` / the Windows build, `python-pyvips` in the AUR
`PKGBUILD`, a `python3-pyvips` Flatpak module). When the installed
libvips can stream a file's format (`pyvips_can_stream` in
`progressive_loader.py`), `TiledPixelStore.from_path` decodes with
`access="sequential"` directly to disk, bypassing
`MAX_SUPPORTED_IMAGE_DIMENSION` (65536) entirely — no full-frame decode
buffer at all. The PIL/imagecodecs path stays as the fallback and keeps the
`65536px` bound. **Format caveat (2026-08):** the bundled `pyvips-binary`
libvips (Flatpak/Windows) has **no libjxl**, so `.jxl` keeps the bounded
imagecodecs path there; distro libvips (AUR/dev) includes libjxl and streams
JXL. HEIF/AVIF/WebP/JPEG/PNG/TIFF/GIF stream via pyvips everywhere.

## Budgeted progressive tile upload (GIMP-style)

Status: **implemented** (2026-07-25). Both `TileResidencyRealizer.realize_tile_plan` (owned by `RhiResources` as `.residency`)
(image_compare) and `BaseImagesPass._realize_tile_residency` (multi_compare)
used to upload **every** currently-missing tile in `target` synchronously,
in the same call/frame that discovered them. On a zoomed-in
`LIVE_TILE_EXTENT`-sized grid over an 18000px+ source, a single pan/zoom
step that shifts the visible window across several tile boundaries at once
could trigger uploading N tiles (each up to ~268 MB pre-crop, crop itself is
cheap but `uploadTexture` + driver-side copy is not free) in one go — a
visible stutter/frame hitch, distinct from (and on top of) the CPU
dispatch-storm issue fixed earlier by `CoalescedFlush`.

GIMP's tile cache does the analogous thing by never blocking a redraw on a
full-resolution fetch: it draws what's already resident immediately, and
lets missing tiles trickle in over subsequent idle-loop iterations,
scanning in a fixed order (top-left outward) so the user perceives
progressive fill-in rather than a freeze.

### Why this is safe to add without touching drawing code

Confirmed by reading `draw_plan.py` and `base_images.py`'s `prepare()`/
`record()`: draw-plan construction is **already** independent of actual GPU
residency for both tabs.

- image_compare: `ensure_srb_for()` falls back to a placeholder texture
  (`self.textures.get(key, placeholder)`) for any tile key not yet uploaded.
- multi_compare: `prepare()` appends `srb=None` for a missing `tile_key`,
  and `record()` skips the draw call entirely when `srb is None`.

So a tile that stays non-resident for a few extra frames just means that
tile's screen region keeps showing the placeholder / previous content one
or a few more frames — no crash, no geometry mismatch, no new
placeholder/skip-path code needed anywhere in either draw plan.

### Mechanism

`target` (the visible+margin tile-index set) is already recomputed from
scratch on every call to `realize_tile_plan` / `_realize_tile_residency` —
there's no persistent queue. A tile left un-uploaded this call is simply
still in `target` (or its replacement) on the next call and gets picked up
then, so the budgeted version is a strict subset filter on the existing
per-call upload loop, not a new async pipeline.

1. `TileTextureService.select_upload_batch()` (`shared/rendering/
   tile_texture_service.py`) orders a `missing` set by distance from
   `visible_rect`'s center (nearest first — mirrors GIMP's inside-out
   perceived fill) and truncates to `budget`. Distance is computed from
   each tile's region center (`grid.iter_regions()`) to the visible rect's
   center, plain Euclidean since tiles are uniform. Pure selection: no
   residency side effects, consistent with the class's existing "decides,
   never touches a GPU texture" contract. Falls back to a deterministic
   sort (no distance computation) when the source has no registered grid
   or no `visible_rect` was given.

2. Both `realize_tile_plan` and `_realize_tile_residency` split their
   `target` loop in two passes: first mark already-resident indices
   touched and collect the rest into `missing`, then call
   `select_upload_batch(key, missing, visible_rect,
   TILE_UPLOAD_BUDGET_PER_CALL)` and only upload that returned `batch`.
   `protected_by_key[key] = target` still uses the **full** target, not
   just `batch` — tiles still pending upload stay eviction-protected, or a
   budget-starved source could never make progress (evict-then-reselect
   thrash).

3. Self-correcting re-request: both realize functions are called from
   `render()` every actual paint, but `QRhiWidget` only repaints on
   `update()` — with no further user input after a budget-limited call,
   nothing would otherwise trigger the follow-up call that picks up the
   rest. Each function now calls `widget.update()` (`renderer.host.update()`
   in multi_compare) itself when `len(batch) < len(missing)`, scheduling
   the next frame so the progressive fill-in keeps moving without further
   wheel/pan input. No pending-queue state or cancellation logic needed —
   panning away from a tile before its budget slot arrives simply drops it
   from `target` on the next call, same as the all-at-once path already
   handled a pan interrupting an in-flight upload set.

### Budget constant

`shared/rendering/tile_constants.py`: `TILE_UPLOAD_BUDGET_PER_CALL = 2`, a
flat tile count next to `TILE_RESIDENCY_MARGIN`. Not bytes: at
`LIVE_TILE_EXTENT = 8192`, a single RGBA8 tile is ~268 MB pre-crop-cost-
dominated already, so a byte budget would degenerate to "0 or 1 tile" in
practice while adding a second unit (bytes vs. count) to reason about.
`2` matches "one tile finishing this frame, one starting"; the exact value
is a profiling knob, not load-bearing for correctness.

**Resolved (2026-07-25):** `select_upload_batch`'s nearest-first ordering
did degenerate to an arbitrary order whenever multiple tiles tied on
distance from center (any full ring around the focus point, not just the
first full-grid population this note originally called out) — `missing` is
a Python `set`, whose iteration order is hash-based, not spatial, and
`sorted(missing, key=_distance)` preserved that hash order for ties instead
of a stable spatial sweep. Fixed by tie-breaking on `(row, col)` as a
secondary sort key, so equal-distance tiles now fill in a fixed order
instead of what looked like a random tile-by-tile pattern during zoom/pan.
Test: `tests/render/test_tile_texture_service_upload_batch.py
::test_equal_distance_ties_break_by_index_not_set_hash_order`. Note the
`len(missing) <= budget` fast path (returns `list(missing)` unsorted) is
untouched — irrelevant there since every tile in `missing` uploads within
that same call regardless of order.

### Call sites changed

| File | Function | Change |
|---|---|---|
| `src/shared/rendering/tile_texture_service.py` | `select_upload_batch()` | new method |
| `src/shared/rendering/tile_constants.py` | `TILE_UPLOAD_BUDGET_PER_CALL` | new constant |
| `src/tabs/image_compare/canvas/rhi_renderer/resources.py` | `realize_tile_plan` (multi-tile branch) | filter `target` → `missing` → `batch`; `widget.update()` when tiles remain outstanding |
| `src/tabs/multi_compare/scene/passes/base_images.py` | `_realize_tile_residency` | same filter shape; `renderer.host.update()` when tiles remain outstanding |

The 1×1-grid fast paths in both functions (the common, non-tiled case) are
untouched — budgeting only applies where `grid.rows > 1 or grid.columns >
1`, i.e. only for sources actually exceeding `LIVE_TILE_EXTENT`.

### Tests

- `tests/render/test_tile_texture_service_upload_batch.py` — pure
  `select_upload_batch` unit tests: under-budget passthrough, zero
  budget/empty missing, nearest-first ordering and truncation, unregistered
  source fallback, no residency side effects.
- `src/tabs/image_compare/tests/render/test_realize_tile_plan_budget.py` —
  a 1200×800 store at `max_tile_extent=512` (6 tiles) asserts the first
  `realize_tile_plan` call uploads exactly `TILE_UPLOAD_BUDGET_PER_CALL`
  tiles and calls `widget.update()`, and that repeated calls against the
  same `target` monotonically fill in the remaining tiles.
- `src/tabs/multi_compare/tests/render/test_realize_tile_residency_budget.py`
  — same shape against `_realize_tile_residency`.
- Existing multi-tile residency tests (`test_tiled_rendering_phase2.py`,
  `test_multi_compare_tiling.py`) kept passing unmodified — their fixtures
  only ever have ≤2 tiles in `target`, at or under the default budget.

## Time-boxed upload budget (+ evaluated: smaller `LIVE_TILE_EXTENT`)

Status: **Part A implemented** (2026-07-25), **Part B evaluated and rejected
(2026-07-25)** — see [Part B findings](#part-b-findings-2026-07-25) below.
`LIVE_TILE_EXTENT` stayed at `8192` as a result of this section (later
changed to `512` by `tile-array-atlas-plan.md` Phase 3 (private, `improve-imgsli-internal-docs`, `docs/legacy/rendering/`), once the array/instanced draw path removed
the draw-call-explosion concern Part B raised below). Follow-up to the
section above —
count-based budgeting shipped, but a live trace of a real zoom session
(`trace.jsonl`, wheel-scroll on an 18000px+ pair) still showed main-thread
stalls up to **2.2s** at tile-grid boundary crossings. Root cause: the two
premises the count-based budget stood on don't hold at our tile size.

### Evidence from the trace

`input.wheel.end` / `input.mmove.end` themselves report `duration_ms` under
1ms almost always (the tracer wraps `mouseMoveEvent`/`wheelEvent` directly).
The stalls show up as **gaps between consecutive input records** with no
nested trace entries in between (paint/`realize_tile_plan` isn't
instrumented) followed by a burst of queued `mmove.end` events draining
instantly — the signature of the main thread being blocked inside an
untraced call, not of any single traced handler being slow. Largest gaps
observed: 2217ms, 1838ms, 1722ms, 1613ms, all at wheel positions repeating
across several events (continuous zoom, not idle time between scrolls).

### Why the count-based budget doesn't bound this

`TILE_UPLOAD_BUDGET_PER_CALL = 2` bounds tile *count*, not the work each
tile costs. At `LIVE_TILE_EXTENT = 8192`, one RGBA8 tile is ~268 MB, so a
"budgeted" call can still synchronously crop + `uploadTexture` up to ~512 MB
in the same call/frame — the exact shape of hitch the budget was meant to
prevent, just at a coarser granularity (every other tile-boundary crossing
instead of every one).

### GIMP/GEGL precedent (researched 2026-07-25)

Two decisions in GEGL's design map directly onto this, and neither is what
we did:

1. **Storage tile size is small — `128×64` px (~32 KB) by default** —
   four orders of magnitude smaller in area than `LIVE_TILE_EXTENT=8192`
   (~268 MB). No single tile touch can be expensive; the *operation graph*
   evaluates larger ROIs (e.g. 2048×4096 for OpenCL kernels, to amortize
   launch overhead) but that's compute batching layered on top of small
   storage granularity, not the storage granularity itself.
2. **The async display path budgets by measured time, not by a fixed
   item count.** `GimpProjection`'s progressive render moved from pure
   idle-rendering to an *adaptive chunk size*: it tracks how much got
   processed in the previous tick and resizes the next chunk to target a
   minimum frame rate, rather than committing to "N units" up front.

Both apply here independently of each other — one is a granularity change,
the other is a scheduling-policy change — and only the second is required
to fix the immediate stalls; the first improves the ceiling.

### Plan

**Part A — time-boxed budget.** Status: **implemented**. Replaces the flat
`TILE_UPLOAD_BUDGET_PER_CALL` count as the loop's real stop condition in
`TileResidencyRealizer.realize_tile_plan` (owned by `RhiResources` as `.residency`) / `BaseImagesPass._realize_tile_residency`
with a wall-clock cutoff: `select_upload_batch`'s nearest-first ordering is
still used to pick candidates (perceived fill-in order, and an upper bound
on how many tiles are even attempted — `TILE_UPLOAD_BUDGET_PER_CALL` stays
as a backstop), but before each tile's `upload_whole`/`_upload_tile` call
the loop checks `time.monotonic()` against a deadline computed once at the
top of the call (`TILE_UPLOAD_TIME_BUDGET_MS = 8.0`, half a 16.6ms/60fps
frame) and breaks — without uploading that tile — once it's passed. The
deadline is shared across every key/layer in the same call (bounds total
per-frame tile-upload time, not per-source fairness); `protected_by_key`
already used the full `target` (not just `batch`) so tiles skipped by the
time check are still eviction-protected and picked up next call exactly
like tiles skipped by the count budget were. No change to
`TileTextureService`, or the self-scheduling `widget.update()`/
`renderer.host.update()` — both are agnostic to *why* a call stopped early.

**Part B — shrink `LIVE_TILE_EXTENT` (evaluated, rejected — see findings
below).** Original proposal: lower the GPU residency tile size (candidate:
8192 → 2048, a 16x reduction in per-tile bytes to ~16 MB) so a *single* tile
upload can't dominate a time budget even without Part A's early-exit saving
it. Not free: smaller tiles multiply the draw-plan cross product
(`_visible_tile_pairs`) and the number of live `QRhiTexture`/SRB objects for
the same viewport, both called out as the reason `LIVE_TILE_EXTENT` was set
high in [Host vs GPU tile granularity](#host-vs-gpu-tile-granularity).

Part A alone should already eliminate the observed multi-second stalls
(each call now yields well under a frame instead of "0, 1, or 2 tiles"
regardless of cost); Part B was meant to lower how bad a worst case can
still be if the time check itself is coarse (e.g. one tile's
`uploadTexture` blocking on the GPU driver past the check). The profile
below shows that trade isn't worth it at any candidate size tried.

### Part B findings (2026-07-25)

Before touching the constant, an unrelated drift bug was found and fixed as
due diligence: `multi_compare/scene/resources.py`'s `SLOT_LIVE_TILE_EXTENT`
was a forked literal (`8192`), not derived from `tile_constants
.LIVE_TILE_EXTENT` — uncaught by any existing contract test, since
`test_tile_constants.py` only checked `image_compare`'s re-export. Fixed by
aliasing it directly and extending
`test_reexports_alias_tile_constants` to pin the equality, so any future
`LIVE_TILE_EXTENT` change can't silently diverge between the two tabs.

With that fixed, a pure-Python analytical profile (`TileTextureService
.register_source()` / `.visible_tiles()` directly, no GPU/Qt needed —
replicates `_visible_side_image_rect`'s center-pan zoom UV math inline: a
one-off ad-hoc script, not checked into the repo, re-derivable from the two
functions named here) measured visible-tile count, draw-plan cross product
(`tiles_per_side²`, matching `_visible_tile_pairs`), and resident VRAM
across two huge-source sizes (18000×12000, 24000×16000), all six zoom
levels tested (1.0, 1.5, 2.0, 4.0, 8.0, 16.0), and three tile-extent
candidates (8192 current, 4096, 2048). Full, actually-run numbers (all
cells measured, none extrapolated):

| Source | Zoom | te=8192 draws | te=4096 draws | te=2048 draws |
| --- | --- | --- | --- | --- |
| 18000×12000 | 1.0 | 36 | 225 | 2916 |
| 18000×12000 | 1.5 | 36 | 225 | 784 |
| 18000×12000 | 2.0 | 36 | 81 | 400 |
| 18000×12000 | 4.0 | 4 | 9 | 36 |
| 18000×12000 | 8.0 | 4 | 1 | 36 |
| 18000×12000 | 16.0 | 4 | 1 | 4 |
| 24000×16000 | 1.0 | 36 | 576 | 9216 |
| 24000×16000 | 1.5 | 36 | 256 | 2304 |
| 24000×16000 | 2.0 | 36 | 64 | 576 |
| 24000×16000 | 4.0 | 4 | 16 | 64 |
| 24000×16000 | 8.0 | 4 | 16 | 16 |
| 24000×16000 | 16.0 | 4 | 16 | 16 |

Two corrections versus the first pass at this analysis: high zoom does
**not** converge to the same draw count regardless of `te` — at
24000×16000 zoom≥8, `te=8192` still holds steady at 4 draws while
`te=2048` sits at 16, because the grid keeps subdividing the same visible
area into more, smaller cells. And the scaling law is not quadratic: since
`tiles_per_side` itself is a 2D count (∝ 1/te²) and draws are that value
squared again (cross product of two images), draws scale as
`(8192/te)⁴`, not `(8192/te)²` — confirmed exactly by the data (te=2048 is
a 4x shrink, and 9216/36 = 256 = 4⁴, matching 576/36 = 16 = 2⁴ for te=4096).
Shrinking `LIVE_TILE_EXTENT` lowers a single tile's worst-case byte cost
(the thing Part B set out to fix) but the draw-call cost grows *much*
faster than the byte-cost falls whenever both compared sources are large
enough to be simultaneously tiled — worst observed case 24000×16000 @
zoom=1.0: **36 → 9216 draw calls**, a 256x increase, at `te=2048`. `te=4096`
is milder (16x) but still a real regression at exactly the low-zoom,
both-sides-tiled case this system exists to handle well.

**Conclusion: reject Part B, keep `LIVE_TILE_EXTENT = 8192`.** Part A
already removes the acute multi-second-stall symptom (the actual user-facing
bug) by bounding *time* instead of tile count, independent of per-tile byte
size. Part B's proposed fix addresses a secondary, harder-to-observe
concern (the time check itself being coarse if one `uploadTexture` call
blocks past its deadline) at the cost of reintroducing a *worse*, more
frequently triggered problem (draw-call explosion on exactly the large,
multi-image workloads this app targets). No evidence in the trace or this
profile justifies that trade. If per-tile upload latency is independently
shown to still cause stalls after Part A (i.e. Part A's time check is
observed tripping late because a single `uploadTexture` call itself doesn't
yield), the better lever is capping bytes-per-call directly (e.g. skip/defer
tiles above a byte-size threshold within `select_upload_batch`) rather than
lowering the storage grain everywhere, since that only pays the draw-call
cost when it's actually needed.

The draw-call cross product itself (not per-tile upload cost) is the real
blocker on ever shrinking `LIVE_TILE_EXTENT` — it's fundamental to today's
one-`QRhiTexture`-per-tile, one-draw-call-per-tile-pair model, not
something Part A/B's scope could fix. See
`tile-array-atlas-plan.md` (private, `improve-imgsli-internal-docs`, `docs/legacy/rendering/`) for the design that
would remove that constraint (texture array + instanced draw) before a
smaller tile size is revisited.

### Tests (Part A)

- `src/tabs/image_compare/tests/render/test_realize_tile_plan_budget.py::test_time_budget_stops_upload_before_count_budget`
  — monkeypatches `resources.time.monotonic` to a clock that's already past
  the deadline on the first in-loop check; asserts zero tiles upload (fewer
  than `TILE_UPLOAD_BUDGET_PER_CALL` would've allowed) and `widget.update()`
  still fires.
- `src/tabs/multi_compare/tests/render/test_realize_tile_residency_budget.py::test_time_budget_stops_upload_before_count_budget`
  — same shape against `_realize_tile_residency` / `base_images.time`.
- Existing count-budget tests in both files kept passing unmodified — real
  wall-clock time for a tiny in-test crop+fake-upload never approaches 8ms,
  so `select_upload_batch`'s count cap is still what's observed there.

### Part B: what was actually done

- Fixed the `SLOT_LIVE_TILE_EXTENT` constant-fork drift bug in
  `multi_compare/scene/resources.py` (aliases `tile_constants
  .LIVE_TILE_EXTENT` now); extended
  `test_reexports_alias_tile_constants` in
  `tests/contracts/test_tile_constants.py` to pin it.
- Ran the analytical draw-call/VRAM profile described in
  [Part B findings](#part-b-findings-2026-07-25) above; no change made to
  `LIVE_TILE_EXTENT` itself based on the result.

## Summary of the invariant

Registration (`register_source`), residency (`realize_tile_plan`), and the
draw plan (`_visible_tile_pairs`) all go through the same
`TileTextureService` grid and the same `visible_tiles`/viewport-rect
computation. As long as a texture key's grid is registered before either
residency or the draw plan run against it, "what's GPU-resident" and "what
the draw plan expects to sample" can't silently diverge — that agreement is
the entire point of centralizing grid state in `TileTextureService` instead
of letting residency and drawing each recompute it independently.
