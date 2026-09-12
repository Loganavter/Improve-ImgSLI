# image_compare State Slot Manifest

Inventory of every `state_slots` key owned by the `image_compare` session
(declared in `src/tabs/image_compare/plugin.py::get_session_blueprints`,
factories resolved by the core slot API in
`src/core/store_workspace.py`). Docs only — no code.

Slot storage itself (`set/ensure/get_session_state_slot`) is core-owned and
is the sanctioned writer path for *slot replacement*; in-slot mutations must
additionally go through `Dispatcher.dispatch` → registered slot reducer
(`src/tabs/image_compare/bootstrap_reducers.py`). A "direct writer" below is
any writer that bypasses both (bare `setattr`/assignment on slot content or
on the live session) — flagged, not blessed.

| Slot name | Owner | Writer path | Readers | Persisted where (project schema keys) | Notes |
|---|---|---|---|---|---|
| `image_compare.state` (`ImageCompareState`, `src/tabs/image_compare/models.py`) | image_compare tab (`use_cases/persistence.py`) | Core slot API: `store.set_session_state_slot("image_compare.state", …)` in `snapshot_into` / `deserialize_session` (emit_scope=None). NOT dispatch/reducer — slot replacement only. | `restore_from`, `serialize_session` (`use_cases/persistence.py`) | `show_file_names`, `edit_name_1`, `edit_name_2`, `camera.{zoom,pan_x,pan_y}` (`serialize_session` v2) | `show_file_names` is **DEPRECATED-pending-removal**: the canonical source is `viewport.render_config.include_file_names_in_saved` (toolbar + `update_toolbar_states` + filename-overlay feature already read the Store, not this flag). A parallel worker removes the field; do not add new readers. |
| `document` (`DocumentModel`, `src/tabs/image_compare/state/document.py`) | image_compare tab | (1) Core slot API: `set_session_state_slot("document", …)` in `use_cases/persistence.py::_write_document` / `deserialize_session`, `services/video_snapshot_rendering/store_rebuild.py`, `services/snapshot_render_plan_builder.py`, `canvas/presentation/snapshot_store.py`, `services/document_store_ops.py`. (2) Dispatch/reducer: `DocumentReducer.reduce` (`bootstrap_reducers.register_state_slot_reducer("document", …)`) via `SetCurrentIndexAction` / `AppendImageItemsAction` / `store.transact(…, scope="document")`. DIRECT WRITERS (flagged): `use_cases/persistence.py::_write_document` fallback `setattr(session, "document", doc)`; `use_cases/slot.py:322` fallback `setattr(<document slot>, "current_index…", …)` for dispatcher-less fake stores. | `widget.py`, `use_cases/{unify,slot,image_decode,navigation,session_bootstrap,chrome_sync}.py`, `ui/{context_menu,transient_flyouts}.py`, `services/{image_export/*,playlist_components/*,live_snapshot,analysis/cached_diff}.py`, `presenters/image_canvas/view.py`, `canvas/presentation/live_presentation.py`, `plugins/video_editor/services/recorder.py` | `image_list1/2[]` (`{path,display_name,rating}`), `current_index1/2`, `image1_path`, `image2_path` | Pixel data is never persisted — only source paths; `rehydrate_session` is demand-driven (O(1), decodes current index only). |
| `pipeline` (`PipelineCacheState`, `src/tabs/image_compare/state/models.py`) | image_compare tab | (1) Dispatch/reducer: `PipelineCacheReducer.reduce` (`bootstrap_reducers.register_state_slot_reducer("pipeline", …)`) via `PutPixel/PutPreview/PutUnified/EvictPipeline/ClearAllCaches` actions. (2) Core slot API init: `set_session_state_slot("pipeline", PipelineCacheState())` in render/contract tests and snapshot builders. | `pipeline/pipeline.py`, `use_cases/{image_decode,chrome_sync,loading_toast,persistence}.py` (`collect_pixel_cache_sources`), `ui/context_menu.py`, `canvas/presentation/live_presentation.py`, `canvas/features/magnifier/{workers/scene_update,geometry/drawing_coords}.py`, `presenters/image_canvas/background_parts/use_cases/{preview,bg_dirty}.py`, `services/{image_export/context_builder,analysis/cached_diff,playlist_components/list_operations}.py` | Not persisted (runtime cache only; rebuilt from `document` paths on demand) | Single source for pixel/preview/unify tiers; `ClearAllCachesAction` resets to empty. |

Related non-slot state restored alongside the slots by
`src/tabs/image_compare/session_persistence.py::restore_viewport_block`
(documented here because the project `viewport` blob carries it):

* `viewport.render_config` — dispatch-only via appearance/session/magnifier
  actions (`SetIncludeFileNamesInSavedAction`, `SetFontSizePercentAction`,
  …, `SetMagnifierMovementInterpolationMethodAction` for
  `interactive_movement_interpolation_method`). Gap: `jpeg_quality` has no
  dedicated Action/reducer, so live restore intentionally leaves it at the
  current value (still serialized; round-trips once an action exists).
* `viewport` image-state prefs (`auto_calculate_psnr/ssim`) — dispatch-only
  via `SetAutoCalculatePsnrAction` / `SetAutoCalculateSsimAction`, else
  `QTimer.singleShot` defer while the dispatcher is unbound. No `setattr`
  fallback remains on any path.
* Post-restore toolbar sync — `refresh_filename_overlay_toolbar(store,
  presenter=None)` reuses `update_toolbar_states` /
  `_sync_filename_overlay_toolbar_state`; called at the end of both the
  immediate and the `QTimer`-deferred dispatch completions.
