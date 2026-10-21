# image_compare State Slot Manifest

Inventory of every `state_slots` key owned by the `image_compare` session
(declared in `src/tabs/image_compare/plugin.py::get_session_blueprints`,
factories resolved by the core slot API in `src/core/store_workspace.py`).
Docs only — no code.

Slot storage itself (`set/ensure/get_session_state_slot`) is core-owned and
is the sanctioned writer path for *slot replacement*; in-slot mutations must
additionally go through `Dispatcher.dispatch` → registered slot reducer
(`src/tabs/image_compare/bootstrap_reducers.py`). A "direct writer" below is
any writer that bypasses both (bare `setattr`/assignment on slot content or
on the live session) — flagged, not blessed.

| Slot name | Owner | Writer path | Readers | Persisted where (project schema keys) | Notes |
|---|---|---|---|---|---|
| `image_compare.state` (`ImageCompareState`, `src/tabs/image_compare/models.py`) | image_compare tab (`use_cases/persistence.py`) | Core slot API: `store.set_session_state_slot("image_compare.state", …)` in `snapshot_into` / `deserialize_session` (emit_scope=None). NOT dispatch/reducer — slot replacement only. | `restore_from`, `serialize_session` (`use_cases/persistence.py`) | `camera.{zoom,pan_x,pan_y}` (`serialize_session` v3) | Side-slot holds **only the camera snapshot**. The UI duplicates `show_file_names` / `edit_name_1` / `edit_name_2` were removed: the canonical "file names enabled" flag is `viewport.render_config.include_file_names_in_saved` (toolbar, canvas filename_overlay, export, caption panel all read the Store); caption texts come from `DocumentModel` display names, synced by the caption editor via `chrome_sync`. Legacy v2 keys are ignored on read. |
| `document` (`DocumentModel`, `src/tabs/image_compare/state/document.py`) | image_compare tab | (1) Core slot API: `set_session_state_slot("document", …)` in `use_cases/persistence.py::_write_document` / `deserialize_session`, `services/document_store_ops.py`, `services/video_snapshot_rendering/store_rebuild.py`, `services/snapshot_render_plan_builder.py`, `canvas/presentation/snapshot_store.py`. (2) Dispatch/reducer: `DocumentReducer.reduce` (`bootstrap_reducers.register_state_slot_reducer("document", …)`) via `SetCurrentIndexAction` / `AppendImageItemsAction` / `SetImageListAction` / `SetCropOverrideAction`, `store.transact(…, scope="document")`. DIRECT WRITER (flagged): `use_cases/persistence.py::_write_document` fallback `setattr(session, "document", doc)` for dispatcher-less fake stores (allowlisted `PENDING_MIGRATION` in `tests/contracts/test_no_setattr_store_bypass.py`); `use_cases/slot.py` fallback `setattr(<document slot>, "current_index…", …)`. | `widget.py`, `presenters/image_canvas/{signatures,view}.py` + `background_parts/use_cases/*`, `use_cases/{unify,slot,image_decode,navigation,session_bootstrap,chrome_sync}.py`, `ui/{context_menu,transient_flyouts}.py`, `services/{document_store_ops,live_snapshot,analysis/*,playlist_components/*,image_export/*,video_snapshot_rendering/*}.py`, `canvas/presentation/*`, `canvas/texture_parts/crop_clip.py`, `plugins/video_editor/services/recorder.py` | `image_list1/2[]` (`{path,display_name,rating,crop_override}`), `current_index1/2`, `image1_path`, `image2_path` | `crop_override` is a plain tristate (`None` == Auto, `True`/`False` == force), all writes via `SetCropOverrideAction` + `DocumentReducer` (`dataclasses.replace`). Pixel data is never persisted — only source paths; `rehydrate_session` is demand-driven (O(1), decodes the current index only). |
| `pipeline` (`PipelineCacheState`, `src/tabs/image_compare/state/models.py`) | image_compare tab | (1) Dispatch/reducer: `PipelineCacheReducer.reduce` (`bootstrap_reducers.register_state_slot_reducer("pipeline", …)`) via `PutPixelAction`/`PutPreviewAction`/`PutUnifiedAction`/`EvictPipelineAction`/`ClearAllCachesAction`. (2) Core slot API init: `set_session_state_slot("pipeline", PipelineCacheState())` in render/contract tests and snapshot builders. | `pipeline/pipeline.py`, `use_cases/{image_decode,chrome_sync,loading_toast,persistence}.py` (`collect_pixel_cache_sources`), `ui/context_menu.py`, `canvas/presentation/{plan_builder,live_presentation}.py`, `canvas/features/magnifier/{workers/scene_update,geometry/drawing_coords}.py`, `presenters/image_canvas/background_parts/use_cases/{preview,bg_dirty}.py`, `services/{image_export/context_builder,analysis/cached_diff,playlist_components/list_operations}.py` | Not persisted (runtime cache only; rebuilt from `document` paths on demand) | Single source for pixel/preview/unify tiers; `ClearAllCachesAction` resets to empty. |

Related non-slot state restored alongside the slots by
`src/tabs/image_compare/session_persistence.py::restore_viewport_block`
(documented here because the project `viewport` blob carries it):

* `viewport.render_config` — dispatch-only via appearance/session/magnifier
  actions (`SetIncludeFileNamesInSavedAction`, `SetFontSizePercentAction`,
  …, and the `overlay.settings.set_movement_interpolation` capability alias
  for `interactive_movement_interpolation_method`). Gap: `jpeg_quality` has
  no dedicated Action/reducer, so live restore intentionally leaves it at the
  current value (still serialized; round-trips once an action exists).
* `viewport` image-state prefs (`auto_calculate_psnr/ssim`) — dispatch-only
  via `SetAutoCalculatePsnrAction` / `SetAutoCalculateSsimAction`, else
  `QTimer.singleShot` defer while the dispatcher is unbound. No `setattr`
  fallback remains on any path.
* Post-restore toolbar sync — `refresh_filename_overlay_toolbar(store,
  presenter=None)` reuses `presenters.toolbar.state.update_toolbar_states`
  (which fans out to the canvas feature binding sync); called at the end of
  both the immediate and the `QTimer`-deferred dispatch completions. Returns
  `bool` and logs a warning on any miss, so an early-bootstrap stale button
  is visible rather than silent.
