# Tiled rendering design of record

The contract behind the GPU tile pipeline: who decides *which* pixels a frame
needs, who decides *how* they become resident, and which knob each of the
three canvases is allowed to set. This is the page code comments point at when
they cite `TILED_RENDERING_DESIGN.md`; the mechanics of the grid, the apron,
the upload budget and the fallback-LOD mechanism are documented in
[tile-rendering-system.md](tile-rendering-system.md), and the pass lifecycle
that hosts them in [render-pass-contract.md](render-pass-contract.md).

Read this before adding a residency knob, a per-tab tiling behaviour, or a new
consumer of `TileTextureService`. The single question to answer first: is the
change *which* geometry/spec a canvas needs (tab) or *how* residency happens
(engine)? Getting that split wrong is how the three consumers below drifted
apart.

**Citation shorthand** (used in tables; prose spells paths out):
`tile_constants.py`, `residency.py`, `fallback_lod.py`, `draw_plans.py`,
`tile_coverage.py`, `tile_texture_service.py`, `first_frame_gate.py`,
`display_tier_service.py` = `src/engine/cache/`; `tiled_image_view.py`,
`array_draw.py`, `array_resources.py`, `base_images_pass.py`,
`host_texture_cache.py` = `src/engine/gpu/`; `ic/…` =
`src/tabs/image_compare/canvas/rhi_renderer/`; `mc/…` =
`src/tabs/multi_compare/scene/passes/`; `mc/scene/…` =
`src/tabs/multi_compare/scene/`; `rhi_backend.py` = `src/ui/canvas_infra/rhi/`.

## Why code comments say "Phase N"

The citations predate this page's rewrite and name sections of its earlier
phased form. The mapping, so a reader who follows one lands somewhere real:

| Cited as | Means today | Section |
|---|---|---|
| Phase 0 | backend texture-size ceiling (`query_max_texture_size`) | [§3](#3-the-policy-matrix-as-measured) |
| Phase 2 | viewport-driven residency, texture-array draw plan, per-tile pairing | [§1](#1-the-contract-engine-decides-how-the-tab-decides-which), [§3](#3-the-policy-matrix-as-measured), [§4](#4-the-one-draw-call-invariant) |
| Phase 3 | anisotropic crop window — tiled export/snapshot render targets | [§5](#5-where-to-change-what) |
| Phase 4 | magnifier multi-tile capture (a capture circle can straddle tiles) | [§2](#2-the-three-consumers-and-their-knobs), [§5](#5-where-to-change-what) |

Other phases named in code (`Phase 1`, `Phase 9`, `Phase 11`) belong to the
private `tile-array-atlas-plan.md`, not to this page.

## 1. The contract: engine decides *how*, the tab decides *which*

The seam is two hooks and one dataclass, in `src/engine/gpu/base_images_pass.py`:

- `BaseImagesSpecHooks.resolve_specs(ctx) -> list[ResidencySpec]`
  (`src/engine/gpu/base_images_pass.py:339`) — the tab builds this call's
  residency specs from its own geometry/LOD model.
- `BaseImagesSpecHooks.upload_tile(tile_service, key, index, tile_image, updates, dirty_layers, region)`
  (`src/engine/gpu/base_images_pass.py:355`) — the tab uploads *one* cropped
  tile into whatever backing store it owns (shared texture array, plain
  per-tile texture, per-tile host cache).
- `ResidencySpec(key, grid, visible_rect, crop_source)`
  (`src/engine/cache/residency.py:58`) — the only vocabulary the seam carries.
  A spec is "this key, this grid, this pixel rect of the source, crop from
  here". It says nothing about budgets, deadlines, eviction or draw order.

The engine half is `TileResidencyRealizerBase.realize_specs`
(`src/engine/cache/residency.py:100`): per spec it resolves the target tile set
(visible rect + `TILE_RESIDENCY_MARGIN` ring), marks the **full** target
eviction-protected, plans a centre-out batch, uploads round-robin across all
specs under one shared wall-clock deadline, warms pages for what it could not
upload, and finally evicts over budget. `BaseImagesPass`
(`src/engine/gpu/base_images_pass.py:361`) is the pass that feeds it
(`realize` at `:424`) and adds no second loop — see that module's docstring
(`:14`, "This module defines no second loop").

Rules that follow from the split:

1. **Tab code never re-implements the loop.** If a canvas needs a different
   *order* or *budget*, that is an engine change with a new knob, not a private
   upload loop in the tab. The one historical exception is documented and
   closed: both tabs used to carry the loop twice
   (`src/tabs/image_compare/canvas/rhi_renderer/residency.py:1`).
2. **The engine never names tab geometry.** Per-slot pan/fit/zoom, letterbox
   mapping, pyramid-level choice and the magnifier's capture window all arrive
   as `ResidencySpec`s; the engine only reads `grid` and `visible_rect`.
3. **Residency and the draw plan must agree on the visible set.** Both consume
   the same `TileTextureService` grid
   (`src/engine/cache/tile_texture_service.py:280`), which is why
   `register_source` (`:182`) is the single write point for geometry — see
   [tile-rendering-system.md](tile-rendering-system.md) "`TileTextureService` —
   grid bookkeeping".
4. **Only `slot_for(key, index) is not None` means drawable.** A spec target is
   a *want*; an array slot is a *have*. Every consumer filters its draw plan
   through the slot lookup (`src/engine/cache/draw_plans.py:329`,
   `src/tabs/multi_compare/scene/passes/base_images.py:750`,
   `src/engine/gpu/tiled_image_view.py:1045`), and coverage accounting must use
   the same predicate (`src/engine/cache/draw_plans.py:177` — the caller hands in
   the actually-resident subset).

## 2. The three consumers and their knobs

### Image Compare — `RhiCanvasRenderer` (fixed pair)

Where its policy lives:

- per-frame entry + spec resolution: `realize_tile_plan`
  (`src/tabs/image_compare/canvas/rhi_renderer/residency.py:700`), including the
  magnifier's separate `capture_uv_rect` residency call;
- LOD commit and settle: `commit_lod_keys`
  (`src/tabs/image_compare/canvas/rhi_renderer/use_cases/lod_commit.py:82`);
- atomicity / first-paint decisions: `ic/use_cases/fallback.py:218` and
  `apply_first_paint_hold`
  (`src/tabs/image_compare/canvas/rhi_renderer/use_cases/coverage.py:438`);
- coarsest-LOD pin: `ic/use_cases/tile_residency.py:320`.

Knobs it sets: 100 ms LOD fetch settle, atomic content swap / LOD level change /
hires flip, first-paint hold, coarsest-LOD pin, 2 GiB GPU tile budget, 3 GiB
host texture cache, derived array capacity (2032 layers).

Hardening the others lack: the **first-paint atomic hold** (no partial plan on
screen until both sides cover and nothing is pending), the **hires-flip hold**
(`stored_*` ↔ `source_*` counts as one tier change), and the **coarsest-LOD
pin** that keeps the loupe's low-res sampling source and the fallback baseline
undestroyable under budget pressure.

### Multi Compare — `BaseImagesPass` (dynamic N slots)

Where its policy lives:

- per-call entry: `residency.realize`
  (`src/tabs/multi_compare/scene/passes/residency.py:694`) building a per-call
  `_SlotUploadRealizer` (`:477`) over the merged engine pass;
- spec build (per-slot LOD resolved exactly once per frame): `build_slot_specs`
  (`src/tabs/multi_compare/scene/passes/residency.py:231`);
- content swap machine: `resolve_swap_spec` / `apply_swap_spec`
  (`src/engine/gpu/base_images_pass.py:138`, `:233`);
- fallback + tier hold: `_is_level_hold`
  (`src/tabs/multi_compare/scene/passes/base_images.py:222`) and
  `_prepare_array_plan` (`:593`).

Knobs it sets: level-change atomicity, per-call LOD commit with **no** settle
window (`src/tabs/multi_compare/scene/passes/residency.py:381`), 512 MiB GPU
tile budget, 512 MiB host tile cache, byte-derived array capacity (508 layers).

Hardening the others lack: the **plain/array split** (a slot that never became
multi-tile keeps per-tile plain textures), the **idempotent swap intake**
(`resolve_swap_spec` returns `None` for a duplicate same-frame upload,
`src/engine/gpu/base_images_pass.py:152`), and the 1×1-preview → multi-full
**backfill** (`:297`) that keeps the preview drawable underneath the new grid.
It deliberately has no first-paint hold
(`src/tabs/multi_compare/scene/passes/base_images.py:714`) — coverage is always
evaluated, and the startup placeholder that covers the canvas until the first
real frames belongs to the tab widget
(`src/tabs/multi_compare/ui/canvas_widget.py:506`), not to the pass.

### Gallery Quick Look — `SingleImageTiledView` (one source, one slot)

Where its policy lives: one engine-owned view,
`src/engine/gpu/tiled_image_view.py` — `set_source`
(`src/engine/gpu/tiled_image_view.py:520`), `_render_single_level` (`:715`),
`_render_multi_level` (`:804`), `LodPolicy` (`:266`). The QL host only chooses
the policy object (`src/tabs/image_gallery/ui/quick_look/preview_canvas/rhi_entry.py:504`).

Knobs it sets: `LodPolicy(mode="settle")` when the demand policy asks for it
(settle debounce defaults to 0 ms, `src/engine/gpu/tiled_image_view.py:285`),
honest `covered`, 2 GiB GPU tile budget (the constant Image Compare also
imports), full 2048-layer array capacity.

Hardening the others lack: an **honest `covered`** — true only when the selected
target level is fully resident, its mip cascade drained, and no fallback is
being drawn (`src/engine/gpu/tiled_image_view.py:968`) — plus **fail-closed
identity**: a tile with no slot is skipped, never substituted by a neighbour
(`:1211`). It has no host texture cache (it crops straight from the level's
pixel store) and no atomic content swap.

## 3. The policy matrix, as measured

Every number below was read out of the constant/derivation at the cited line.
"none" means the consumer has no such knob at all — that is the drift this page
exists to surface, not an oversight to paper over.

| Knob | Image Compare | Multi Compare | Quick Look | Code |
|---|---|---|---|---|
| Live tile extent | 512 px | 512 px (alias) | 512 px | `tile_constants.py:32`, `mc/scene/resources.py:55` |
| LOD settle | 100 ms (`LOD_FETCH_SETTLE_MS`) | none — per-slot LOD committed immediately | `LodPolicy(mode="settle")`, `settle_ms = 0` | `tile_constants.py:112`, `ic/use_cases/lod_commit.py:181`; `mc/residency.py:381`; `tiled_image_view.py:285`, `src/tabs/image_gallery/ui/quick_look/preview_canvas/rhi_entry.py:504` |
| Atomicity | content swap **+** hires flip **+** level change | level change only | none (progressive; settle substitutes) | `ic/use_cases/fallback.py:239`; `mc/base_images.py:222`, `:703`; `fallback_lod.py:27`, `tiled_image_view.py:949` |
| First-paint hold | yes (placeholder cleared until covered + nothing pending) | none | none (raster/cover plate until `covered`) | `ic/use_cases/coverage.py:438`, `ic/renderer.py:454`; `mc/base_images.py:714`; `tiled_image_view.py:449`, `src/tabs/image_gallery/ui/quick_look/preview_canvas/rhi_entry.py:338` |
| Coarsest-LOD pin | yes | **none** | **none** | `ic/use_cases/tile_residency.py:320` → `tile_texture_service.py:497` |
| GPU tile budget | 2 GiB | 512 MiB | 2 GiB | `tiled_image_view.py:112` (IC imports it: `ic/residency.py:43`, used `:329`); `mc/scene/resources.py:56`; `tiled_image_view.py:426` |
| Host texture cache budget | 3 GiB | 512 MiB | **none** (crops from the store) | `host_texture_cache.py:14` via `ic/residency.py:905`; `mc/scene/resources.py:57` → `mc/base_images.py:388` |
| Array capacity (layers/array) | 2032 (derived) | 508 (derived) | 2048 (flat cap) | `ic/resources.py:81`; `mc/base_images.py:78`; `tiled_image_view.py:107` |
| Array-index guard | pair-equality only | explicit `array_index != 0` drop | **none** (index discarded) | `draw_plans.py:355`; `mc/base_images.py:754`; `tiled_image_view.py:1048`, `:1212` |
| Upload count budget | 64 / key / call | 64 / key / call | 64 / key / call | `tile_constants.py:60`, `residency.py:147` |
| Upload time budget | 12.0 ms / call | 12.0 ms / call | 12.0 ms / call | `tile_constants.py:80`, `src/engine/cache/tile_upload_budget.py:41` |
| Mip cascade budget | 8.0 ms / frame | 8.0 ms / frame | 8.0 ms / frame | `tile_constants.py:95` |
| Residency margin | 1 tile ring | 1 tile ring | 1 tile ring | `tile_constants.py:132` |
| Apron | 1 px | 1 px | 1 px | `tile_constants.py:40` |
| First-frame present gate | 10 presents | 10 presents | its own cover settle | `first_frame_gate.py:20`; `src/tabs/image_gallery/ui/quick_look/preview_canvas_host/cover.py:347` |

Capacity derivations (both compare tabs compute, they do not hardcode):

- Image Compare, `ic/resources.py:81`: `min(DEFAULT_MAX_ARRAY_SIZE,
  max(3 × tiles_per_axis², tile_budget // layer_bytes))` with
  `_MAX_EXPECTED_CANVAS_PX = 4096` (`:70`), `_ARRAY_LAYER_PX = 512 + 2×1 = 514`
  (`:48`) → `tiles_per_axis = ceil(2×4096/512) + 1 = 17`, `layer_bytes = 1 056 784`,
  `2 GiB // layer_bytes = 2032`, so `min(2048, max(867, 2032)) = 2032`. The ×3 is
  image1 + image2 + diff.
- Multi Compare, `mc/base_images.py:78`: same shape without the ×3 →
  `max(289, 512 MiB // layer_bytes = 508)` → 508.
- Quick Look, `tiled_image_view.py:107`: `DEFAULT_MAX_ARRAY_SIZE`
  (`tile_texture_service.py:21`) verbatim — no canvas or byte clamp, so its
  array can pre-size 2048 layers.

Read the matrix as a to-do list, not a scoreboard. The coarsest pin and the LOD
settle are the two knobs with the clearest one-consumer-only story: both were
added for Image Compare symptoms (loupe sampling, wheel-scroll fetch storms)
and both would help Multi Compare, which currently re-resolves and re-fetches a
slot's level immediately on every frame (`mc/residency.py:381`).

## 4. The one-draw-call invariant

A frame issues **one** instanced draw per array pass, not one per tile pair:
`record_array_draw` → `draw_array_instances` → `command_buffer.draw(4, instance_count)`
(`src/engine/gpu/array_draw.py:259`). Everything a tile needs to be drawn must
therefore fit in the per-instance vertex attributes.

Two facts make the array index non-negotiable:

1. `ArrayInstance` (`src/engine/gpu/array_draw.py:73`) carries `layer1`,
   `layer2`, `layer_diff` and **no `array_index`**. The GPU resource owner can
   open additional arrays (`_ensure_tile_array`,
   `src/engine/gpu/array_resources.py:178`), but
2. the array SRB binds **only `tile_arrays[0]`** at binding 1
   (`src/engine/gpu/array_resources.py:260`), and `ensure_array_srb` never
   re-binds when a second array appears (`:232`).

Consequence — the invariant every consumer must honour: **a plan item whose
slot lives in array ≥ 1 must not be emitted.** Its layer number addresses a different texture
object than the one bound, so drawing it samples an unrelated layer of array 0
(wrong content, no error, no seam to notice).

Where the rule is enforced today:

- Multi Compare drops it explicitly: `if array_index != 0: continue`
  (`src/tabs/multi_compare/scene/passes/base_images.py:754`) — the reference
  implementation of the guard.
- Image Compare emits `ComparePairPlan.array_index`
  (`src/engine/cache/draw_plans.py:77`) but the plan builder only skips pairs
  whose **two sides** disagree (`array_index2 != array_index1`, `:355`); the
  adapter then drops the field when it builds
  `ArrayDrawItem` → `ArrayInstance`
  (`src/tabs/image_compare/canvas/rhi_renderer/use_cases/draw.py:175`). Two
  sides that both landed in array 1 pass through and would sample array 0.
- Quick Look unpacks and discards the index
  (`src/engine/gpu/tiled_image_view.py:1048`, `:1212`).

So the invariant holds by capacity arithmetic, not by a guard, in two of the
three consumers. `_TileSlotAllocator.allocate`
(`src/engine/cache/tile_texture_service.py:66`) opens array *N+1* the moment a
live key would exceed `max_array_size`, so this is reachable as soon as a
consumer's capacity assumption is wrong (a canvas wider than 4096 px in the
compare tabs' derivation, or any QL source that exceeds 2048 live layers).
Converging on Multi Compare's `!= 0` drop is the cheap hardening; widening the
SRB to an array-of-arrays is the expensive one.

## 5. Where to change what

| Change | Where it goes | Why |
|---|---|---|
| New residency/budget knob (count, deadline, margin, eviction policy) | `src/engine/cache/tile_constants.py` + `src/engine/cache/residency.py` | one loop, one deadline, all consumers inherit it |
| New per-tab geometry or LOD model | the tab's `resolve_specs`/`build_slot_specs` (`ic/residency.py`, `mc/residency.py:231`, or `tiled_image_view.py` for QL) | the engine must stay unable to name tab geometry |
| New content-swap behaviour | `resolve_swap_spec` / `apply_swap_spec` (`base_images_pass.py:138`, `:233`) + tab hooks | the decision is engine, the effects are tab-bound |
| New fallback-LOD promotion rule | `src/engine/cache/fallback_lod.py:19` (shared) | all three consumers call it; a per-tab copy is how the coverage bug got duplicated |
| New letterbox/content geometry | `update_common_letterbox_geometry` (`src/engine/cache/display_tier_service.py:359`) | single owner of the eager `max(w1,w2), max(h1,h2)` envelope |
| New comparison-pair shader (IC diff/base) | `src/tabs/image_compare/canvas/shaders/base_array.vert.qsb` / `.frag.qsb` pair + `array_draw.ARRAY_INSTANCE_*` | the per-instance layout is the engine contract; the pair shaders stay tab-owned |
| New slot shader (MC / QL) | `src/engine/gpu/shaders/slot_array.vert.qsb` / `.frag.qsb` + `array_draw.SLOT_INSTANCE_*` | one instanced draw carries the whole transform per instance |
| New mip-downsample behaviour | `src/engine/gpu/mip_cascade.py` + its `.qsb` | the cascade drains per frame under `MIPS_CASCADE_TIME_BUDGET_MS` |
| New tiled export/snapshot geometry | `src/engine/gpu/export_tiling.py` + `pack_base_uniforms`'s `viewport_zoom`/`viewport_offset` (`ic/uniforms.py:36`) | the anisotropic crop window is the same uniforms with an override, not a second shader |
| Tile size / backend ceiling | `LIVE_TILE_EXTENT` (`tile_constants.py:32`) + `query_max_texture_size` (`rhi_backend.py:732`) | fixed constant so eviction is machine-independent; the clamp comes from the backend |

## Related

- [tile-rendering-system.md](tile-rendering-system.md) — grid bookkeeping,
  apron, upload budget, fallback-LOD mechanics, host-memory bounding.
- [render-pass-contract.md](render-pass-contract.md) — the pass lifecycle that
  hosts these loops.
- [display-image-pipeline.md](display-image-pipeline.md) — which roles get
  texture-uploaded, and the preview tier.
- [rendering-model.md](rendering-model.md) — live path vs snapshot/export path.
