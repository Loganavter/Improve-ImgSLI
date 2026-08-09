# Display image pipeline: preview tier → unify → pyramid → tiled render

How a loaded image pair goes from disk to the textures the QRhi canvas
draws. The old full-image "display cache" (a PIL downscale of the unified
pair) is gone; its role is served by the mipmap pyramid over the tiled
store — see [tile-rendering-system.md](tile-rendering-system.md).

## Lifecycle of a pair

1. **Preview tier** (`document.preview_image1/2`, ≤1024px) — decoded first,
   shown immediately. Exists before any memmap store; never part of the
   pyramid.
2. **Full decode** (`document.full_res_image1/2`) — background workers.
   A unify of a mixed pair (one side full, other preview) is *deferred*
   while the other side's decode is still in flight
   (`use_cases/loading.py::_defer_mixed_unify`), so we never LANCZOS-upscale
   a 1024 preview to 20k.
3. **Unify** (`_session_controller.py::_unify_images_worker_task`) resizes
   both sides to a common size and wraps the result as memmap-backed
   `TiledPixelStore`s (`image_state.image1/2`). Aborts via `should_abort`
   when superseded by a newer unification task.
4. **Pyramid build** (`_start_pyramid_builds` → `PyramidPixelStore`) —
   levels are built finest-first in a worker, each level published as it
   lands; the coarsest level is ≤1024. Aborts when a newer unification
   supersedes it or the base store closes.
5. **Render** — per frame, `resolve_lod_texture_keys` picks the pyramid
   level for the current on-screen scale (`shared/rendering/lod.py::
   select_level`, shared with snapshot/export for parity), the draw plan
   selects visible tiles, and `realize_tile_plan` lazily crops+uploads
   only those tiles.

## The roles

- **stored_*** — the background/base pair the canvas draws. Chosen by
  `shared/rendering/display_image_picker.py::pick_display_image`: a
  `TiledPixelStore` is only eligible once its pyramid is complete; until
  then the preview tier stays on screen. Single picker — do not hand-roll
  `or`-chains.
- **source_*** — the hi-res pair used when `use_hires` is active and by the
  magnifier (always samples level 0). Same unified coordinate space as
  stored.
- Both roles go through `RhiResources.upload_source`: a 1×1 grid uploads a
  single whole texture; a multi-tile grid uploads nothing eagerly and lets
  `realize_tile_plan` fill residency on demand.

## The preview→store flip

When a pyramid completes, `pick_display_image` flips that side from the
preview to the store; `display_cache_key` changes and the plan applicator
takes the full path (`plan_applicator.py::_apply_plan_full`). Invariants:

- The flip must **not** disturb the viewport: preview and store share one
  normalized coordinate system (same aspect after unify), so zoom / pan /
  letterbox are untouched. `_apply_plan_full` must not reset+restore the
  view for `preserve_zoom` plans — the 2026-07 regression ("камеру кидает
  к ближней грани" at pyramid completion) came exactly from the
  `reset_view()` + restore + `restore_letterbox_focus` dance emitting
  transient zoom/pan through `zoomChanged` listeners.
- `_on_pyramid_level_ready` invalidates the render pick **only when a
  pyramid just completed** (that is the only event that can change
  `pick_display_image`'s answer); intermediate level publishes just
  schedule a repaint so the per-frame LOD selector can use the new level.

## Known costs / open items

- First touch of an 8192² live tile (crop + upload) costs ~0.4s per side.
  Seen when the flip or a deep-zoom boundary crossing first realizes an L0
  tile. Mitigation candidates: smaller `LIVE_TILE_EXTENT` (4096/2048) or
  async tile crops.
- `stored_*` and `source_*` can both point at the same unified store,
  registering the same image under two tile-grid keys (potential duplicate
  GPU tiles when hires mode engages). Candidate for unification into one
  key/role.
- `display_cache_key` is now just a texture-identity signature (uid+size
  pair); the name is historical. `apply_canvas_render_plan` is the live
  plan-apply path (video/export included).
- `display_resolution_limit` setting survives only as an input to
  `downscale_pair_to_limit` users (metrics, background layers, session
  persistence, dialogs) — analysis/export sizing, not the render path.
