# Display image pipeline: preview tier → unify → pyramid → tiled render

How a loaded image pair goes from disk to the textures the QRhi canvas
draws. Written from memory, verify file/line before relying on exact names.

The old full-image "display cache" (a PIL downscale of the unified pair)
is gone; its role is now served by the **mipmap pyramid** over the tiled
store — see [tile-rendering-system.md](tile-rendering-system.md). Preview is
a separate `QImage` ≤1024 backing, unify is tile-native `BICUBIC`, geometry
is an eager `max` envelope.

## Lifecycle of a pair

1. **Preview tier** (`PipelineCache` preview `QImage`, ≤1024px long edge) —
   decoded first via `QImageReader` + `setScaledSize` (`Format_RGBA8888`;
   PIL/imagecodecs only as fallback for JXL/unknown), shown immediately.
   Exists before any memmap store; never part of the pyramid. This is the
   `QImage 1024 backing` that the canvas draws until the pyramid is ready.
2. **Full decode** (`TiledPixelStore`, memmap-backed) — background workers
   via `TiledPixelStore.from_path` (pyvips streaming when available, else
   PIL/imagecodecs full-frame). A unify of a mixed pair (one side full, other
   preview) is *deferred* while the other side's decode is still in flight
   (`use_cases/loading.py::_defer_mixed_unify`), so we never LANCZOS-upscale
   a 1024 preview to 20k.
3. **Unify** (`_session_controller.py::_unify_images_worker_task` →
   `shared/image_processing/pixel_ops/unify.py::unify_pair`) resizes both
   sides to a common size `pw,ph = max(w1,w2), max(h1,h2)` (e.g. `2797` in the
   `21:36 IMGSLI_IC_GAP_DEBUG` trace) tile-native via
   `write_resampled_to_store` (`BICUBIC`, `shared/image_processing/resample_map.py`)
   into memmap-backed `TiledPixelStore`s (`image_state.image1/2`). Small
   outputs (`≤4096²`) fall back to `resize_images_processor` PIL path for exact
   match. Aborts via `should_abort` when superseded by a newer unification
   task.
4. **Pyramid build** (`_start_pyramid_builds` → `PyramidPixelStore`) —
   levels are built finest-first in a worker, each level published as it
   lands; the coarsest level is ≤1024 (`COARSEST_MIN_DIM`). Aborts when a
   newer unification supersedes it or the base store closes. Each level is
   its own `TiledPixelStore` (own memmap), so tile addressing and apron are
   identical at every level.
5. **Render** — per frame, `resolve_lod_texture_keys` picks the pyramid
   level for the current on-screen scale (`shared/rendering/lod.py::
   select_level`, shared with snapshot/export for parity), the draw plan
   selects visible tiles, and `realize_tile_plan` lazily crops+uploads
   only those tiles (budgeted via `shared/rendering/tile_constants.py`).

## Eager max envelope (geometry)

Single owner, eager, no HOLD:

- `canvas/texture_parts/base_images.py:196` `update_common_letterbox_geometry`
  and `presenters/image_canvas/background_parts/render_flow.py:55`
  `_update_comparison_geometry` are the **single geometry owners**. When both
  sides have sizes, they compute `pw,ph = max(w1,w2), max(h1,h2)` once from
  `shared/image_processing/image_dims.py::get_image_dims` and derive a single
  fitted rect via `ui/canvas_infra/scene/frame_geometry.py::
  resolve_canvas_content_geometry(cw,ch,pw,ph)` (`cw,ch` = canvas logical
  size, `pw,ph` = eager envelope). Both letterbox slots receive the same
  `ux/cw, uy/ch, uw/cw, uh/ch`, dispatched via `store.transact`
  (`SetPixmapDimensionsAction` + `SetImageDisplayRectAction`).
- **No `UNION_LETTERBOX_HOLD_MS` / `more_pending` / `Store.predicted_unified_size`
  for geometry.** `HOLD` (`shared/rendering/tile_constants.py:111`
  `UNION_LETTERBOX_HOLD_MS = 350.0`) and `atomic` remain **only for pixels**
  — fallback-LOD in `rhi_renderer/renderer.py:463` (`_resolve_fallback_plan` →
  `resolve_fallback_lod(atomic=True)`). Geometry is stable from the first
  `gap draw_plan` (`IMGSLI_IC_GAP_DEBUG=1`): e.g. `44.007 gap draw_plan`
  already `0.545/1080` (`pw=2797` eager max) and stays `0.545` through
  `full TiledStore → unify → pyramid` — `0` jump, `bbox 0.091` stable
  (previously `0.201/0.596 → 0.226/0.545` jump via HOLD when `predicted`
  arrived 1 fps tick late).
- Fallback to per-image letterbox only when one side has no size (`w==0`);
  otherwise the envelope is identical for image 1 and image 2 (no
  `needs_union` / `grid_mismatch` branching — removed).

## The roles

- **stored_*** — the background/base pair the canvas draws. Chosen by
  `shared/rendering/display_image_picker.py::pick_display_image`: a
  `TiledPixelStore` is only eligible once its pyramid is complete; until
  then the preview tier stays on screen (with optional
  `pick_display_with_preview_backing` freshness guard in `render_flow.py`).
  Single picker — do not hand-roll `or`-chains.
- **source_*** — the hi-res pair used when `use_hires` is active and by the
  magnifier (always samples level 0). Same unified coordinate space as
  stored (both `2797` after eager max).
- Both roles go through `RhiResources.upload_source`: a 1×1 grid uploads a
  single whole texture; a multi-tile grid uploads nothing eagerly and lets
  `realize_tile_plan` fill residency on demand.

## The preview→store flip

When a pyramid completes, `pick_display_image` flips that side from the
preview `QImage` to the `TiledPixelStore`; `display_cache_key` changes and
the plan applicator takes the full path (`plan_applicator.py::_apply_plan_full`).
Invariants:

- The flip must **not** disturb the viewport: preview and store share one
  normalized coordinate system (same aspect after eager `max` envelope), so
  zoom / pan / letterbox are untouched. `_apply_plan_full` must not reset+restore
  the view for `preserve_zoom` plans — the 2026-07 regression ("камеру кидает
  к ближней грани" at pyramid completion) came exactly from the
  `reset_view()` + restore + `restore_letterbox_focus` dance emitting
  transient zoom/pan through `zoomChanged` listeners.
- The flip must be **atomic on screen** for pixels: the preview's tiles stay
  drawn in full until every current-view tile of the store has uploaded, then
  the draw plan flips over in one frame. This is `renderer.py:463` atomic
  fallback (`resolve_fallback_lod(atomic=True)`), not a geometry HOLD — the
  flip commits the store under fresh `LevelKey`s and rekeys nothing, so its
  fallback baseline carries no rekeyed marker — the renderer's content-swap
  detection recognizes it via the source-identity change instead (see
  `src/tabs/image_compare/docs/investigations/content-swap-atomic-commit.md`
  and `docs/dev/rendering/tile-rendering-system.md` "Content swaps are
  atomic; LOD churn is progressive").
- `_on_pyramid_level_ready` invalidates the render pick **only when a
  pyramid just completed** (that is the only event that can change
  `pick_display_image`'s answer); intermediate level publishes just
  schedule a repaint so the per-frame LOD selector can use the new level.

## Known costs / open items

- First touch of a 512-px live tile (crop + upload) is cheap (~1 MB/tile);
  at the old `LIVE_TILE_EXTENT=8192` it was ~0.4s/~268 MB per tile. Deep-zoom
  boundary crossing now realizes via budgeted `TILE_UPLOAD_BUDGET_PER_CALL=64`
  + `TILE_UPLOAD_TIME_BUDGET_MS=12.0` (`shared/rendering/tile_constants.py:111`).
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
