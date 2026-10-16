# Plan — Image Gallery decomposition (controller + widget + remaining large files)

Status: draft · Date: 2026-10-17 · Scope: `src/tabs/image_gallery/` (tab-owned)

Parts: **A** `controller.py` · **B** `widget.py` · **C** remaining gallery files
(grid_view, quick_look package, clean_review, drag_drop, triage, secondary) ·
**D** non-gallery oversized files (triage list only).

Related: [CODE_PATTERNS.md](../../../../../docs/dev/CODE_PATTERNS.md) ·
[FILE_SIZE_POLICY.md](../../../../../docs/dev/FILE_SIZE_POLICY.md) ·
[CODE_MASS_REDUCTION.md](../../../../../docs/dev/CODE_MASS_REDUCTION.md) ·
[README.md](../README.md)

## Why this exists

`src/tabs/image_gallery/controller.py` is **5 044 lines / 155 methods** and
`widget.py` is **2 754 lines / 82 methods**. Both carry an `Audit-Meta:`
exemption, so they are *policy-legal* — but the exemption reason is now
stretched. The `state-machine` reason ("one controller lifecycle — folder
scan/thumbnail/triage/VLM sharing GenericWorker state") only holds for the
folder/worker seams; the file also owns Ask AI, the Jev ranker, the Redux
slot bridge, series overrides, filtering and the bounded scheduler — each an
orthogonal concern with its own entry point. Per `CODE_PATTERNS.md` the
"when not to split" test is: *can you name the split?* Here you can — the
file's own section banners already name every one (see the cluster map).

The whole tab is the repository's mass centre: gallery is **52 316 LOC**
(production, no tests) vs `image_compare` 69 324 and `multi_compare` 17 402,
and **11 of the 20 largest `src/**/*.py` files are gallery files** (top three
overall are `controller.py`, `ui/grid_view.py`, `widget.py`).

## Split criterion (the model to measure every wave against)

A boundary is valid only when **all** hold:

1. **Distinct trigger** — it has one entry point / caller set (a toolbar
   action, a worker signal, a store subscription), not "whatever is left".
2. **Named state read-set** — it reads a small, declarable slice of owner
   state (never `self` wholesale as an excuse for "one machine").
3. **Testable seam** — an existing test or a new focused one exercises it
   through the owner (kitchen-sink `self` fakes are a smell, not a target).
4. **Method-name freeze** — the public/method surface keeps its **names**
   (`CODE_PATTERNS.md` line 69): bodies move to `use_cases/` /
   `ui/<area>_parts/` as `def name(owner, …)`, the class keeps a one-line
   thin delegator. Call sites and the ~1 400 gallery tests do not move.

Anti-goal: a "helpers bag". If two clusters share `self._folder_gen`,
`self._find_item`, `self._tracked`, `self._pool_start`, `self._stage_gate`,
those primitives stay on the owner (or a single shared `_owner` module) —
splitting must not fork the folder-generation / staging discipline.

## Survey — files that grew past 500 lines

`python src/devtools/file_meta.py --report` → **95 files > 500 lines, all
already carrying `Audit-Meta:` / `File-Size-Exempt:`** (no unmarked debt by
policy). The exemptions worth revisiting, gallery first, then the rest of
`src/`:

| Lines | File | Marker | Verdict |
|---|---|---|---|
| 5044 | `tabs/image_gallery/controller.py` | state-machine | split (this plan) |
| 3972 | `tabs/image_gallery/ui/grid_view.py` | state-machine | own epic (item-view + selection + headers in one `QWidget`) |
| 2754 | `tabs/image_gallery/widget.py` | thin-owner | split (this plan) |
| 2014 | `tabs/image_gallery/ui/quick_look/preview_canvas.py` | thin-owner-target | quick-look epic |
| 1840 | `tabs/image_gallery/ui/clean_review.py` | state-machine | own epic |
| 1803 | `tabs/image_gallery/ui/quick_look.py` | thin-owner | quick-look epic |
| 1653 | `tabs/image_gallery/ui/drag_drop.py` | single-router | review (router already one concern) |
| 1649 | `tabs/image_gallery/ui/quick_look/strip.py` | thin-owner-target | quick-look epic |
| 1632 | `tabs/image_gallery/ui/quick_look/preview_canvas_host.py` | thin-owner-target | quick-look epic |
| 1230 | `tabs/image_gallery/use_cases/triage.py` | thin-owner | review |
| 1180 | `tabs/image_gallery/ui/quick_look/resize.py` | thin-owner-target | quick-look epic |
| 1458 | `tabs/image_compare/.../magnifier/render/magnifier_pass.py` | File-Size-Exempt | single QRhi pass — keep |
| 1258 | `engine/cache/display_tier_service.py` | state-machine | review |
| 1245 | `engine/gpu/tiled_image_view.py` | state-machine | keep (one tile-array render lifecycle) |
| 1155 | `tabs/multi_compare/scene/passes/base_images.py` | — | review |
| 1117 | `tabs/image_compare/canvas/widget.py` | thin-owner | review |
| 1040 | `tabs/image_compare/plugins/video_editor/services/thumbnails.py` | state-machine | keep |
| 1033 | `tabs/multi_compare/scene/passes/residency.py` | — | review |
| 986 | `engine/store/tiled_pixel_store.py` | state-machine | keep (one memmap lifecycle) |

The **`ui/quick_look/` package is 11 807 lines across 20 files** — the single
largest subsystem in the tree; it deserves its own epic, not this plan.

---

## Part A — `controller.py` cluster map → target modules

Line ranges are current-start → next banner. `→` = target `use_cases/`
module; the class keeps same-named thin delegators.

| Lines | Cluster (banners) | → target |
|---|---|---|
| 1–330 | module prelude, `_scheduler_thread_count`, `_new_gallery_pool`, `_GalleryVisibilityPauseFilter`, `__init__` | stays (owner ctor + shared) |
| 374–655 | **bounded scheduler** (`schedule`, `sched_stats`, `_tracked`, `_pool_start`, `_schedule_thumbs`, `_begin_folder_schedule`, `_subscribe_visible_range`, `_on_visible_range_changed`, `_install_visibility_pause`, `pause_background`, `resume_background`, `_trim_proxy_cache`) | `use_cases/gallery_scheduler.py` |
| 657–1183 | **gallery slot / Redux** (`_gallery_store`, `bind_gallery_session`, `_is_active_gallery_tab`, `_gallery_slot`, `_emit_gallery`, `_transact_gallery`, `_on_store_changed`, `_sync_from_slot`, `_apply_fusion_ranks`, `_apply_slot_*`, `set_selection`, `set_source`) | `use_cases/gallery_slot.py` |
| 1183–1305 | **coalesced completions** (`_queue_thumb_ready`, `_flush_pending_thumbnails`, `_queue_card_refresh`, `_flush_pending_card_refresh`, `_emit_triage_finished`) | `use_cases/completion_coalescing.py` |
| 1305–1616 | **folder loading** (`open_folder`, `open_paths`, `_on_pick_folder`) + `_find_item` | `use_cases/folder_loading.py` (`_find_item` stays shared) |
| 1616–1677 | **thumbnails** (`_load_thumbnail`, `_on_thumbnail_ready`, `_on_thumbnail_error`) | `use_cases/thumbnails.py` |
| 1677–1898 | **AI analyze / domain** (`analyze_item*`, `hydrate_cached_analysis`, `_hydrate_ai_cache`, `reanalyze_*`, `_set_judgment_domain`, `activate_judgment_domain`, `_run_ai_for_visible`) | `use_cases/ai_analysis.py` |
| 1898–2404 | **Jev ranker + series priority** (`_run_jev_ranks`, `_jev_*`, `_launch_jev_batch`, `_run_series_priority`, `_clear_series_priority`, `_run_jev_rank_for_series`, `_jev_outcome_ok`, `_apply_jev_outcome`, `_degrade_jev`, `_refresh_rank_provenance`) | `use_cases/jev_rank.py` (`_JEV_STAGE` registration stays module-scope) |
| 2404–2533 | **analysis delivery** (`_begin_analysis`, `_apply_ai_phase`, `_on_analysis_ready`, `_on_analysis_error`, `_refresh_open_quick_look`) | `use_cases/ai_analysis.py` |
| 2533–2897 | **Ask AI** (`open_ask_ai*`, `_ask_cache_key`, `ask_ai_question`, `_on_ask_ai_*`, `_show_ask_ai_*`) | `use_cases/ask_ai.py` |
| 2897–3483 | **triage Stage-2 Pass-1** (`_assign_fresh_stable_ids`, `_section_*`, `_restore_singletons`, `_apply_series_view`, `_run_triage_sync`, `retriage_quiet`, `_start_triage`, `_mark_local_pass`, `_settle_metrics_pass`, `_run_ai_on_settle`, `_run_jev_on_settle`, `_queue_ai_rank_on_settle`, `_begin/_finish_append_processing`) | `use_cases/triage_run.py` |
| 3483–3742 | **artifacts + fidelity + camera metrics** | `use_cases/metrics_stage2.py` |
| 3742–4111 | **unified Stage-2 proxy pass** (`_run_proxy_chunk_sync`, `_schedule_proxy`, `_start_proxy_analysis`, `_on_proxy_batch_ready`, `_on_triage_ready`, `_commit_triage_series`, `_apply_triage_result`) | `use_cases/proxy_pass.py` |
| 4111–4371 | **Stage-3 VLM tie-break + briefs** (`_is_tie`, `run_tie_break_if_needed`, `_apply_tie_break_result`, `_apply_brief_result`) | `use_cases/tie_break.py` |
| 4371–4487 | **crown/reject/S3 wrappers** (`make_best`, `toggle_reject`, `remove_*`, `keep_best_of_series`, `show_all`) | `use_cases/triage.py` (extend existing) |
| 4487–4933 | **manual series overrides** (`move_paths_to_series`, `group_paths_as_new_series`, `_attach_append_items`, `_cluster_tail_into_series`, `recluster_series`, `reset_series_overrides`, `clean_rejected`, `show_clean_review`) | `use_cases/series_override.py` (extend existing) |
| 4946–5043 | **filtering** (`set_filter_text`, `apply_pending_filter`, `_apply_filter*`, `_on_brief_filter_ready`) | `use_cases/filtering.py` |

**Residual controller target: ~800–1 100 lines** (`__init__` state model, the
shared primitives, signal wiring, thin delegators). It stays > 500 →
**keep `Audit-Meta:` but reword to `pattern=thin-owner`** once the bodies are
out — the `state-machine` claim no longer applies to the whole file.

## Part B — `widget.py` cluster map → target modules

Widget-side concerns use `ui/widget_parts/` (functions-taking-owner, mirroring
`image_compare/presenters/image_canvas/background_parts/`), not `use_cases/`.

| Lines | Cluster | → target |
|---|---|---|
| 70–410 | `__init__`, signal/child construction | stays (owner) |
| 410–641 | **Redux subscription + render-from-slot** (`_on_filter_text_dispatch`, `_init_gallery_store_subscription`, `bind_gallery_session`, `_render_gallery_*`) | `ui/widget_parts/gallery_slot.py` |
| 641–923 | **toolbar/view/sort/domain + view prefs** (`_on_sort_changed`, `_sort_keyfunc`, `_on_view_toggled`, `_on_domain_changed`, `attach_session_state`, `_persist_view_prefs`, `apply_view_prefs`, `paintEvent`) | `ui/widget_parts/view_prefs.py` |
| 923–1098 | **card interaction + context menus** (`_on_card_toggle`, `_on_empty_host_context`, `_on_card_context`, `_on_empty_file_dropped`) | `ui/widget_parts/card_actions.py` |
| 1098–1280 | **Ask AI surface** (`open_ask_ai`, `_ask_scope_key`, `_submit_ask_ai`, `show_ask_ai_*`, `_resume_ask_ai_if_hidden`) | `ui/widget_parts/ask_ai_surface.py` |
| 1280–1571 | **series headers + naming + retranslate** (`_compute_series_hub_names`, `_on_series_context_menu`, `_rename_series`, `_refresh_series_names`, `_retranslate_*`) | `ui/widget_parts/series_headers.py` |
| 1571–1600 | quick-look hooks | stays (thin, delegates to `ui/quick_look/`) |
| 1600–1671 | **keyboard** (`attach_controller`, `_owner_for_triage`, `keyPressEvent`) | `ui/widget_parts/keys.py` |
| 1700–1816 | **status badges + session view** (`set_scanning`, `set_background_scanning`, `set_triage_done`, `reset_session_view`) | `ui/widget_parts/status.py` |
| 1818–2361 | **grid API + series view restore + card refresh** (`set_folder_label`, `rebuild_grid`, `_restore_series_view`, `_sample_view_frame`, `set_rank_provenance`, `refresh_card(s)`, `sync_source_badge`, `set_card_visible`) | `ui/widget_parts/grid_api.py` |
| 2361–2388 | DnD events (`dragEnterEvent` … `dropEvent`) | `ui/widget_parts/dnd.py` (router lives in `ui/drag_drop.py`) |
| 2388–2754 | **triage actions** (`_on_keep_best`, `_on_show_all`, `_on_clean_rejected`, `_on_compare_finalists`, `_series_view_matches`, `_rebuild_series_view`, `_refresh_action_states`, `set_triage`) | `ui/widget_parts/triage_actions.py` |

**Residual widget target: ~500–700 lines.** Reword its `Audit-Meta:` reason
to "thin owner + `ui/widget_parts/*`" once done.

## Execution order (waves) and gates

One wave = one `use_cases/` (or `ui/widget_parts/`) module + its thin
delegators. Each wave is independently reviewable and revertible; **never
mix two clusters in one wave**.

- **Wave 1 — leaf handlers** (lowest coupling): filtering, thumbnails,
  completion-coalescing, Ask AI. No worker-lifecycle change.
- **Wave 2 — state bridges**: `gallery_slot.py`, `folder_loading.py`,
  `gallery_scheduler.py` (respect the **frozen `schedule` seam** — keep the
  public `schedule` signature verbatim).
- **Wave 3 — pipeline**: `triage_run.py`, `metrics_stage2.py`, `proxy_pass.py`
  (shares `GenericWorker` / `_pool_start` — keep those on the owner).
- **Wave 4 — newest seams**: `ai_analysis.py`, `jev_rank.py`, `tie_break.py`.
  Guard: `tests/contracts/test_gallery_pipeline_substrate.py` asserts the
  `_judgment_domain` authority + the `jev_rank` stage gate — it must stay red
  to a regression after the move.
- **Widget waves** mirror A: slot → view_prefs/status → card_actions/keys →
  grid_api/series_headers → triage_actions.

Per-wave gate (per `FILE_SIZE_POLICY.md` / `CODE_PATTERNS.md`):

1. **Method names unchanged** — `git diff main...<branch> -G "^def "` shows
   only additions of delegators/`use_cases` functions, no renames.
2. `./launcher.sh test tests/contracts -q` green (incl.
   `test_gallery_ownership_guards.py`, `test_gallery_pipeline_substrate.py`,
   `test_file_size_policy.py`).
3. Gallery suite green (`src/tabs/image_gallery` — was 1389 passed / 2 skipped
   with 2 pre-existing ALLOWLIST failures in `test_gallery_ownership_guards.py`
   as of 2026-10-17; those two must be fixed or re-baselined first).
4. `python src/devtools/file_meta.py --write-registry` if any `Audit-Meta:`
   text changes; `python src/devtools/docs_link_graph.py --write-index` if a
   doc moves.

## Risks / guardrails

- **Shared primitives** (`_find_item`, `_tracked`, `_pool_start`,
  `_folder_gen`, `_stage_gate`, generation tokens): stay on the owner; a
  wave may read them through `owner.` but must not duplicate them.
- **Folder-generation discipline**: every worker delivery keeps its
  `_is_current_folder_gen` / `_series_gen` check — moving bodies must not
  drop a stale-drop guard.
- **Session isolation**: `_gallery_session_id` / own-emit accounting must
  move atomically with `gallery_slot.py`, or slot reads regress to "active
  session" (contract `test_gallery_ownership_guards`).
- **Exemptions are enforcement, not decoration**: an oversized unmarked file
  fails CI; a moved body must not leave a stub still > 500 lines without its
  own marker.

## Part C — gallery: remaining large files (cluster maps)

The survey flagged these as own epics; mapped here so each can start without a
second discovery pass. Same criterion + per-wave gate as Parts A/B.

### C1. `ui/grid_view.py` — 3972 lines (`state-machine`)

One `GalleryGridView(QWidget)` (~3150 lines) plus module helpers, filters and
six layer/handle classes. Cluster → target:

| Lines | Cluster | → target |
|---|---|---|
| 78–332 | colour resolvers + Wave-A drag-source (`dragged_paths_for_press`, `build_gallery_drag_mime`, `should_start_gallery_drag`, `resolve/compose_gallery_drag_pixmap`) | `ui/grid_view/drag_source.py` |
| 344–467 | `_CardPressDragFilter`, `_CardKeyFilter` | `ui/grid_view/filters.py` |
| 469–528 | `GalleryGridNavSection` | `ui/grid_view/nav_section.py` |
| 530–820 | layers (`_SeriesHeaderAccentLayer`, `_SeriesDropTargetLayer`, `_BandSeparatorHandle`, `_SeriesCollapseArrowLayer`) | `ui/grid_view/layers.py` |
| 1031–1343 | view mode + column math (`set_view_mode`, `_sync_series_column_widths`, `_compute_columns`, `_adapt_columns_and_reflow`, `_reflow_flat`) | `ui/grid_view/columns.py` |
| 1343–1520 | side-by-side bands + splitter (`_plan_bands`, `_plan_band_entries`, `set_split_left`, `nav_columns_for`) | `ui/grid_view/bands.py` |
| 1520–2065 | keyboard focus nav (`_live_cards_in_order`, `focused_*`, `move_focus`, `handle_navigation_key`, `_focus_snapshot/_restore`) | `ui/grid_view/nav.py` |
| 2065–2284 | rebuild (`rebuild_grid`, `_promote_flat_ungrouped`, `_rebuild_next_chunk`) | `ui/grid_view/rebuild.py` |
| 2374–3453 | series grouping (`set_series`, `_retitle_header`, `_rebuild_series`, `append_new_cards`, `_make_series_header`, `_toggle_collapse`) | `ui/grid_view/series.py` |
| 3512–3666 | pool helpers (`_acquire_card`, `_sync_activity`, `_recycle_card`, `_rebind_card`) | `ui/grid_view/pool.py` |
| 3666–3811 | card drag source (`note_card_press`, `build_card_drag`, `maybe_start_card_drag`) | `ui/grid_view/drag_source.py` |
| 3811–3896 | card/series context-menu dispatch | `ui/grid_view/context.py` |
| 3896–3972 | marquee/external helpers + `eventFilter` | `ui/grid_view/marquee.py` |

Residual `GalleryGridView`: `__init__` + theme slots + `visible_paths` + thin
delegators (~500–700 lines). Watch the coupling: the drag-source helpers and
`_CardPressDragFilter` share `_drag_owner`/`note_card_press` state — move them
together.

### C2. `ui/quick_look/` — 11 807 lines / 20 files (epic)

The package already IS the decomposition of the old monolith; the giants are
two lifecycles (canvas, host), themselves splittable, plus the overlay shell:

| Lines | File | Responsibility | → target |
|---|---|---|---|
| 2014 | `preview_canvas.py` | one `QuickLookCanvasWidget(QRhiWidget)`: source lifetime → tiled single-source → lazy levels → applicator plan → QRhi entry points → frame raster | `quick_look/canvas/` per-phase modules (mirrors `magnifier/`) |
| 1632 | `preview_canvas_host.py` | host glue: preview-store cache, tiled source population, prefetch/warm, cover/first-frame, fallback wiring | `quick_look/host/` (`store_cache.py`, `tiled_source.py`, `prefetch.py`, `cover.py`, `fallback.py`) |
| 1803 | `quick_look.py` | `QuickLookOverlay(TopLevelInWindowOverlay)` shell + region selection | keep shell; region → `quick_look/region.py` (exists) |
| 1649 | `strip.py` | filmstrip: wheel/lasso/repin filters + strip paint + `rebuild_strip` | `quick_look/strip/` (`filters.py`, `paint.py`, `rebuild.py`) |
| 1180 | `resize.py` | overlay resize: border/ring zones + cursors + report-row relayout | `quick_look/resize/` (`zones.py`, `cursors.py`, `relayout.py`) |
| 971 | `metrics.py` | metric rows + cache + domain read | `quick_look/metrics/` (`rows.py`, `cache.py`) |
| 951 | `overlay_build.py` | overlay UI construction (`build_overlay_ui` + plate widgets) | keep (one builder) |

**Epic** — the canvas and host lifecycles each need their own criterion pass;
do not attempt as a single wave.

### C3. `ui/clean_review.py` — 1840 (`state-machine`)

- 71–827 `_ReviewPlate(QWidget)` — its `paintEvent` alone is ~222–826
  (~600 lines) → `ui/clean_review/plate.py`.
- 827–1840 `CleanReviewOverlay` — `_populate` (1354–1696, ~340) + row building
  → `ui/clean_review/populate.py`; shell/interaction stays.

### C4. `ui/drag_drop.py` — 1653 (`single-router`)

Split the ~670-line series-band **drop-target geometry** out of the router:

- 38–980 routing (`is_acceptable_drop`, `drag_*_event`, `_route_paths`,
  `drop_event`, `_ZoneDropFilter`, header reset menu) → stays (router).
- 981–1653 geometry (`_section_bands`, `_section_band_target`,
  `series_target_at`, `_card_hit_series`, `_header_at`, `_grid_has_headers`)
  → `ui/drag_drop/targets.py`.
  `test_gallery_dnd_delivery.py` pins `series_target_at`/`_header_at` — keep names.

### C5. `use_cases/triage.py` — 1230 (`thin-owner`)

Already functions-taking-owner; split by concern into a package: Redux emit
helpers (41–184) → `triage/emit.py`; provenance (226–322) →
`triage/provenance.py`; crown/reject (323–525) → `triage/crown.py`;
removal/reinsert (525–844) → `triage/removal.py`; moves (704–885) →
`triage/moves.py`; `compare_finalists`/aliases/`show_all` (885–1201) →
`triage/compare.py`. (This is also Part A Wave-3's extension target.)

### C6. Secondary gallery files (brief verdicts)

| Lines | File | Split |
|---|---|---|
| 923 | `ui/toolbar.py` (`compound-widget`) | sort flyout (787→) + the two container classes → `ui/toolbar_parts/` |
| 861 | `services/ai_client.py` (`wire-client`) | parsing (`_parse_*`, 132–295) vs transport (`call_sync`/stream, 342–660) → `ai_parse.py` / `ai_transport.py` |
| 742 | `ui/stats_strip.py` (`compound-widget`) | theme resolvers (26–188) → `ui/stats_strip_parts/theme.py` |
| 710 | `ui/ask_ai.py` (`single-surface`) | flyout is one surface — keep |
| 685 | `services/artifacts.py` (`tiled-pipeline`) | stateless detector kernels — keep |
| 654 | `ui/card/context_menu.py` | target predicates (107–320) vs popup build → `card/context_parts/` |
| 596 | `ui/quick_look_hooks.py` | **fix its stale ALLOWLIST entries first** (Wave-1 blocker) |
| 505 | `ui/card.py` | builders already flat — keep |

## Part D — non-gallery large files (triage list, NOT verdicts)

These belong to other tabs / the host, so their cluster maps go in *their* docs
(`src/tabs/<tab>/docs/`) or `docs/dev/CODE_MASS_REDUCTION.md` — this plan only
flags them. **No verdict is asserted here**: per `CODE_PATTERNS` "code first,
comments last", each must be opened before deciding keep vs split.

| Lines | File | Marker | Note |
|---|---|---|---|
| 1458 | `image_compare/.../magnifier/render/magnifier_pass.py` | File-Size-Exempt | single QRhi pass — likely keep |
| 1258 | `engine/cache/display_tier_service.py` | state-machine | candidate: upload/geometry vs legacy-plan apply |
| 1245 | `engine/gpu/tiled_image_view.py` | state-machine | one tile-array lifecycle — likely keep |
| 1155 | `tabs/multi_compare/scene/passes/base_images.py` | — | candidate (1 class, MC render pass) |
| 1116 | `tabs/image_compare/canvas/widget.py` | thin-owner | verify it still delegates per `CODE_PATTERNS` |
| 1039 | `video_editor/services/thumbnails.py` | state-machine | one pipeline — likely keep |
| 1033 | `tabs/multi_compare/scene/passes/residency.py` | — | candidate |
| 985 | `engine/store/tiled_pixel_store.py` | state-machine | one memmap lifecycle — keep |
| 937 | `engine/gpu/glass_panel.py` | state-machine | keep |
| 925 | `plugins/help/dialog.py` | qdialog-wiring | keep |
| 968 | `video_editor/services/video_export/service.py` | state-machine | keep |
| 915 | `image_compare/.../rhi_renderer/residency.py` | tile-residency | keep |
| 759 | `image_compare/presenters/toolbar/connections.py` | state-machine | review |

## Sequencing (all parts)

Parts A/B are the primary target (the tab's two hubs). Then, cheapest-isolated
first: **C4** (drag targets) → **C5** (triage package) → **C6** (secondary) →
**C3** (clean_review) → **C1** (grid_view) → **C2** (quick_look package, epic).
Part D is a separate host/other-tab track; nothing here blocks it.
