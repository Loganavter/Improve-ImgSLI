# Investigation: content replacement must be atomic, not tile-by-tile

Cross-tab mechanism notes live in [docs/dev/rendering/tile-rendering-system.md]
(../../../../docs/dev/rendering/tile-rendering-system.md) ("Fallback-LOD").
This is the tab-local writeup of the per-tile redraw / patchwork-swap bug on
the Image Compare live canvas and its fix.

## User-visible symptom

When the canvas replaces displayed *content* — the preview→store flip after
pyramid completion, or loading a new image into an already-loaded slot — the
user sees the new image appear tile-by-tile over several frames: a patchwork
mix of old and new regions, or (worst case) blank holes. Not a clean,
one-frame replacement.

## Mechanism (why the mix happens)

Per-frame flow in `RhiCanvasRenderer.render()` (canvas/rhi_renderer/
renderer.py): `resolve_lod_texture_keys` picks the pyramid `LevelKey`s,
`realize_tile_plan` registers/refills the new content's grid under the
per-frame upload budget, `build_array_draw_plan` builds the current (partial)
tile plan, and `resolve_fallback_lod` decides whether to draw the previous
baseline underneath. The last step has an `atomic=True` mode (shared/rendering/
fallback_lod.py) that hides the new content's tiles until every current-view
tile is resident, then flips the whole draw plan over in one frame. That mode
is exactly the required behavior — but it was only ever *enabled* when the
fallback baseline carried a rekeyed old-content marker, and two of the three
content-swap paths produced baselines that the marker check did not recognize:

1. **Same-slot lazy swap** (both contents `TiledPixelStore`): `realize_tile_plan`'s
   re-register branch rekeys the old content to `("_content_stash", key, uid)`
   (canvas/rhi_renderer/residency.py `_rekey_or_restore`). The renderer's
   content-swap check only looked for `("_prev_content", ...)` — the marker
   produced by the *eager* whole-image path (`rekey_stale_content`, e.g. the
   diff role). The lazy path's marker fell through ⇒ `atomic=False` ⇒
   `drop_covered_fallback_items(fallback, current) + current` ⇒ new tiles
   drawn on top of the old content as each one uploads.

2. **Preview→store flip**: the preview tier is a plain PIL source under the
   bare slot keys (`"stored_0"`/`"stored_1"`); the flip commits the store
   under fresh `LevelKey("stored_0", L)` keys. The new grid is *new*, so
   `realize_tile_plan` rekeys nothing — `last_rekeyed_keys` is empty, no
   marker exists anywhere, and the baseline is just the previous frame's
   plain bare keys remembered in `_last_good_texture_keys`. The marker check
   could not see it, so the flip ran non-atomic: the old preview stayed as a
   fallback under the new LevelKey tiles and the store content revealed
   tile-by-tile over it (the "mid-frame tile redraw" — each frame redraws
   with a few more new tiles popped in).

A plain LOD/pyramid-level churn (zoom crossing a level boundary, same source)
must stay progressive — that is the intended reveal. The distinguishing
signal is *source identity*: content swaps change the source objects
(`source_ids` from `image_uid(sources)`), LOD churn never does.

## Fix (renderer.py `_resolve_fallback_plan`)

- Marker detection now recognizes both rekeyed marker forms:
  `_is_rekeyed_content_key` accepts `("_prev_content", ...)` and
  `("_content_stash", ...)`.
- A new persisted flag `_content_swap_active` is set on the frame a source
  identity change commits (preview→store flip, lazy same-slot swap,
  source-role switch) while a fallback baseline exists and differs from the
  current keys, and cleared on promotion. This covers the flip, which has no
  marker at all.
- `resolve_fallback_lod`'s atomic branch (shared) now degrades to drawing the
  partial new content when the old-content fallback plan comes back empty
  (nothing old left to hold the screen) instead of a blank frame.
- The fallback-decision block was extracted from `render()` into
  `_resolve_fallback_plan(...)` so the whole decision is unit-testable
  without a live QRhi.

## Frame-by-frame decision table

2797×2304 store, tile extent 512 ⇒ 6×5 = 30 tiles/side; upload budget
`TILE_UPLOAD_BUDGET_PER_CALL` + `TIME_DEADLINE` (time-boxed per frame).

| Frame | State | Before fix — draw plan | After fix — draw plan |
|---|---|---|---|
| N−1 | preview fully resident | old preview (bare keys) | old preview (bare keys) |
| N (flip) | store grid registered, ≤budget tiles uploaded | fallback (preview, ~98%-covered tiles dropped) **+** 1–30 new LevelKey tiles ⇒ mixed frame | **atomic**: preview only — every non-resident region draws old content |
| N+1 … N+k | tiles uploading (budget-limited) | more preview tiles dropped as coverage grows; new tiles pop in ⇒ per-frame patchwork redraw | preview only, unchanged across frames |
| N+k+1 | all current-view tiles resident (`more_pending=False`) | switch — last-good promoted | switch in **one frame** — the entire plan is the new content |

Same-slot store→store swap is identical, with `("_content_stash", ...)` /
`("_prev_content", ...)` markers carrying the baseline. A pure LOD level
change keeps `atomic=False` and the old progressive reveal in both versions.

## Tests

`src/tabs/image_compare/tests/render/test_content_swap_atomic_commit.py`:

- `test_preview_to_store_flip_is_atomic_and_commits_in_one_frame` — full
  flip frame sequence with budgeted uploads: every mid-transition plan binds
  old-content layers only and covers the whole visible rect (no blank, no
  new-tile mix); commit happens in a single frame once resident.
- `test_same_slot_lazy_swap_stash_marker_is_atomic` — the `_content_stash`
  marker must trigger atomic mode (this test failed on the old
  `_prev_content`-only check).
- `test_same_slot_swap_commits_in_one_frame_once_resident` — promotion and
  flag clearing once the new content is resident.
- `test_lod_level_churn_stays_progressive` — regression guard: a plain LOD
  churn still reveals progressively and never sets the flag.