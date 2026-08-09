"""Single source of truth for tile sizing shared by host and GPU layers.

Contract (docs/dev/rendering/tile-rendering-system.md): a GPU live tile must
cover a whole number of host pixel tiles, so host-tile reads compose GPU
uploads without partial-tile seams. ``AppConstants.PIXEL_TILE_SIZE`` mirrors
``PIXEL_TILE_SIZE`` — the import direction (core must not import
shared.rendering) forbids sharing the object, so a contract test pins the
values equal (tests/contracts/test_tile_constants.py).
"""

# Host pixel tile edge (TiledPixelStore addressing).
PIXEL_TILE_SIZE = 512

# GPU live-tile edge for the interactive canvas renderer. Fixed constant
# rather than backend-derived so tile count (and therefore eviction and
# residency behavior) is deterministic across machines.
#
# Industry-standard deep-zoom tile size (Google Maps/Slippy Map, OpenSeadragon
# DZI, Zoomify, IIIF all use 254-512px tiles), not the 8192 this used to be.
# 8192 was a stopgap from before the texture-array instanced-draw path
# (docs/dev/rendering/tile-array-atlas-plan.md) existed: the old one-draw-
# call-per-tile-pair path scaled draw calls as (8192/te)^4, so shrinking the
# tile size there was rejected (see docs/dev/rendering/tile-rendering-system.md
# "Time-boxed upload budget (+ evaluated: smaller LIVE_TILE_EXTENT)"). The
# array path removed that blocker (one instanced draw regardless of tile
# count) but LIVE_TILE_EXTENT itself was never revisited (tile-array-atlas-
# plan.md Phase 3 was left open) until a real user report of an 8192-tile
# (~268 MB/tile) LOD transition needing 2x its resident set simultaneously
# (old + new level, straddling a tile boundary) to avoid perpetual
# evict/re-upload thrashing between levels -- a cost that's ~impossible with
# a tile two orders of magnitude smaller.
LIVE_TILE_EXTENT = 512

# Default max tile extent for TileTextureService grids (offscreen/export).
DEFAULT_TILE_EXTENT = 16384

# Real neighboring source pixels duplicated on every tile edge so bilinear
# filtering at a tile boundary samples true neighbor data instead of
# ClampToEdge-repeating its own edge texel (a visible seam otherwise).
TILE_APRON_PX = 1

# Upper bound on how many missing tiles a single residency-realization call
# will even attempt, independent of TILE_UPLOAD_TIME_BUDGET_MS below (docs/
# dev/rendering/tile-rendering-system.md "Budgeted progressive tile
# upload"). Exists only as a backstop against a pathologically fast/no-op
# upload path defeating the time check by never tripping it. At the old
# LIVE_TILE_EXTENT=8192 (~268 MB/tile) the time budget below was always what
# stopped the loop first, so this stayed a low flat number without ever
# mattering in practice; at today's 512px tiles (~1 MB each) it's the other
# way around -- 8ms comfortably fits far more than 2 uploads, so a low count
# here would now be the actual (and needlessly slow) fill-rate bottleneck.
# Tiles left over stay in the caller's `target` set and get reconsidered
# (nearest-first) on the next call -- no separate queue needed.
TILE_UPLOAD_BUDGET_PER_CALL = 64

# Wall-clock budget (milliseconds) for tile uploads within a single
# realize_tile_plan / _realize_tile_residency call (docs/dev/rendering/
# tile-rendering-system.md "Planned: time-boxed upload budget"). A flat tile
# *count* doesn't bound cost -- one LIVE_TILE_EXTENT tile is ~268 MB, so
# "budgeted" calls could still synchronously move hundreds of MB. The loop
# checks elapsed time after each tile and stops once this is exceeded,
# regardless of how many tiles that was.
#
# Raised from 8.0 (docs/dev/KNOWN_BUGS.md same-slot-swap SSIM follow-up,
# sixth fix): at today's ~1 MB (512px) tiles, 8ms left a full base+diff
# grid refill after an image swap (e.g. 5x8=40 tiles across stored_0,
# stored_1, and the diff layer) visibly trickling in over multiple
# seconds -- a real cost, not merely a debug-dump artifact (the tile-debug
# JSONL log's own frame-gap timings are unusable here since IMGSLI_TILE_DUMP
# adds its own synchronous per-mip-layer PNG readback+write cost, but the
# tile-count-vs-time progression in `array_draw_plan.result` events holds
# regardless of that contamination). 12ms still leaves ~4.6ms of a 16.6ms
# (60fps) frame for the rest of render() after tile upload work.
TILE_UPLOAD_TIME_BUDGET_MS = 12.0

# Wall-clock budget (milliseconds) for the mip-cascade pass
# (RhiResources.generate_all_dirty_mips) within a single render() call
# (docs/dev/rendering/tile-array-atlas-plan.md Phase 9). Separate from
# TILE_UPLOAD_TIME_BUDGET_MS above -- profiling on a rapid multi-level LOD
# transition found the cascade itself (not just tile upload) costing up to
# ~11ms CPU-submit time at 30+ dirty layers in one frame, enough on its own
# to blow a 16.6ms/60fps frame. Groups (whole (array_index, layer) mip
# chains, never split mid-cascade) left over once this is exceeded are
# carried into next frame's dirty_layers instead of forced through
# synchronously -- a texture's own just-uploaded level-0 content is always
# correct immediately; only its coarser mip levels lag by a frame or two
# until their cascade budget comes up, which is not visually distinguishable
# from the upload itself still being in flight.
MIPS_CASCADE_TIME_BUDGET_MS = 8.0

# Milliseconds a pyramid-level target (resolve_lod_texture_keys' output)
# must stay unchanged before RhiCanvasRenderer.render() actually commits to
# fetching tiles for it (docs/dev/rendering/tile-array-atlas-plan.md Phase 9
# "reduce data volume per transition" finding). A rapid wheel-scroll burst
# crosses several pyramid levels within ~20-50ms of each other (profiled:
# 5 levels in ~250ms) -- without this, render() faithfully launches a fresh
# realize_tile_plan fetch for *every* one of those levels even though most
# are superseded (and their partial uploads evicted) a frame or two later,
# never contributing to a single stable frame. Holding fetch at the last
# *committed* level (still drawn via the existing fallback-LOD path, which
# already tolerates a stale level while a new one loads) until the target
# has been stable for this long means only the level the scroll actually
# lands on gets fetched, not every one it passed through. Zoom/pan state
# itself is never delayed by this -- only which level's tiles render()
# spends upload/mip budget on.
LOD_FETCH_SETTLE_MS = 100.0

# Extra ring of tiles kept GPU-resident beyond what's strictly visible.
# Was 0: that was set when LIVE_TILE_EXTENT was 8192 -- a prefetch ring
# multiplied the resident set ~9x (a single 8192^2 RGBA tile was ~268 MB),
# blowing any realistic byte budget and causing per-frame evict/re-crop
# thrash. At today's 512px tiles a margin of 1 costs a few MB, not hundreds.
# Raised to 1 (docs/dev/rendering/tile-array-atlas-plan.md Phase 9 "zoom
# flash on every single step" finding): at margin=0 the visible rect
# shifting by even one wheel notch immediately needs tiles that were never
# resident (no buffer past the viewport edge), so every zoom/pan step --
# not just cross-LOD transitions -- showed a clear/upload/draw pop-in cycle
# at the newly-exposed edge. A margin of 1 keeps one ring of tiles past the
# edge already resident before the viewport reaches them. Seams within one
# tile are handled by TILE_APRON_PX regardless of this setting.
TILE_RESIDENCY_MARGIN = 1
