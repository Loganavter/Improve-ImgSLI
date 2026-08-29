# Plan: Store/Redux direct mutation elimination and dogma hardening

Status: `In progress` (2026-08-29) — app-wide generation, 60 hits remaining
Area: `src/core/store.py:34`, `src/core/state_management/dispatcher.py:118`, `src/core/state_management/reducers.py:1`, `src/tabs/image_compare/state/reducers.py:50`, `src/tabs/image_compare/use_cases/loading.py:42`, `src/tabs/image_compare/services/document_store_ops.py:1`, `src/tabs/image_compare/services/analysis/metrics.py:1`, `tests/contracts/test_no_direct_store_mutation.py:1`
Related: [STORE.md](./STORE.md) (Action→Dispatcher→RootReducer→Store), [CONTRACTS.md](./CONTRACTS.md) (isolation), [ARCHITECTURE.md](./ARCHITECTURE.md) §State Model, [CODE_PATTERNS.md](./CODE_PATTERNS.md) (thin owner), `tests/contracts/test_viewport_state_slots.py:1`, `tests/runtime/test_reducer_purity_full.py:1`
TODO ref: `docs/dev/TODO.md` → P2 Redux action-shape (blocked, this plan unblocks it); `docs/dev/STORE.md:109` Step 9 (~340 sites)
Skills: `.cursor/skills/imgsli-devtools/SKILL.md` (tracer `IMGSLI_TRACE=1`, contracts `./launcher.sh test tests/contracts -q`, `QT_QPA_PLATFORM=offscreen pytest`), `.cursor/skills/sli-ui-toolkit-docs-first/SKILL.md` (N/A for this plan — Store only, no UI toolkit)

> **Executor note.** Trigger: user-reported preview race — `2026-08-29` log `ic-preview` left occupies right, preview vanishes before `more_pending=False`. Root cause split: GPU fallback/`_resolve_fallback_plan` (`src/tabs/image_compare/canvas/rhi_renderer/renderer.py:376`) needs atomic hold, **and** Store bypass `image_state.image1=u1` (`src/tabs/image_compare/use_cases/loading.py:639`) in `on_unified_images_ready` skips lock/history/emit/session re-point. Prior investigation spawned 4 parallel `explore` subagents that mapped `78` direct `session_data/image_state/render_cache/document` writes outside Reducer. Existing dogma `test_viewport_state_slots.py:40` only scanned `*.viewport.<attr>` depth 1 (slotted check) and missed `image_state.image1` (dataclass, not slotted). This plan hardens the dogma first, then fixes hot-path violations incrementally — mirrors `improve-imgsli-internal-docs/docs/legacy/plan_test_suite_revision.md` and `plan_app_wide_tokenization.md` structure (Goal → Research inventory → Design → Phased Steps → Risks → Progress log). Breaking allowed for dogma; no shim — direct → `dispatch(SetXAction)`.

## 1. Goal and non-goals

**Goal:** zero `store.viewport.session_data.image_state/render_cache` and `document` direct assignments on live `Store` outside `RootReducer`/`Store` impl. Measured: `tests/contracts/test_no_direct_store_mutation.py:1` `78 hits → 0`, `tests/contracts -q` green, `QT_QPA_PLATFORM=offscreen pytest -q` green, `IMGSLI_TRACE=1` dispatch chain shows `dispatch.begin/end` for every former direct site (no orphan `store.emit_state` without `dispatch`).

**Non-goals / do not touch:**
- Step 9 extraction of `ImageSessionState/RenderCacheState` to `state_slots` — this plan keeps them on `ViewportState` (like `STORE.md:109` ~340 sites note) and only fixes mutation path, not shape.
- Rewriting 62 action-class shapes / settings-scalar registry (`TODO.md` P2) — dogma hardening here is prerequisite, not the compression itself.
- `sli-ui-toolkit` painter/QSS (see `sli-ui-toolkit-docs-first` skill — not used; this is Store only).
- Transient `Store()` builders (`src/tabs/image_compare/canvas/presentation/snapshot_store.py:52`, `store_rebuild.py:28`, `snapshot_render_plan_builder.py:97`) — exempted via data-flow tracking (`Store()`-derived `document` etc), not migrated.
- Adding new `ActionType` enum values beyond those already declared (`SetImageSessionImageAction` etc exist in `src/tabs/image_compare/state/reducers.py:50`).

**Locked decisions (do not reopen):**
- Dogma is AST scan in `tests/contracts/` (`_framework.py:23` `iter_py`), not runtime — matches `test_viewport_state_slots.py` and `plan_test_suite_revision.md:53` hermeticity rule.
- `Dispatcher` stays `threading.Lock` non-reentrant (`dispatcher.py:118` doc: `QTimer.singleShot(0, dispatch)` for follow-up) — direct still forbids lock bypass.
- Transient exemption is by construction (`Store()` / `SessionData()` / derived `document = store.get_session_state_slot(...)`) not by file allowlist — avoids hiding live `self.store.viewport...` in same file (`snapshot_render_plan_builder.py:352` live vs `97` transient).
- One owner per invariant (`plan_test_suite_revision.md:63`): this dogma owns Store direct-mutation; `test_viewport_state_slots.py` keeps slotted-shape check.

## 2. Research summary (verified 2026-08-29, full scan — do not re-research)

### 2.1 Inventory — where direct writes live today (78 → 0 narrow, then 60 app-wide after generation)

| Scope | `grep` / AST | Hits | Example file:line |
|---|---|---|---|
| Dogma old | `*.viewport.<attr>` depth1 `test_viewport_state_slots.py:40` | 0 for `image_state` | `src/tabs/image_compare/use_cases/loading.py:639` missed (chain depth 3, dataclass not slotted) |
| Narrow dogma `INTERMEDIATE={session_data,image_state,render_cache,document}` `test_no_direct_store_mutation.py:15` | `78` (exempt `Store`/`Reducer` impl) | `loading.py:639 image_state.image1 = u1` |
| Transient excluded | `Store()`-derived via `_collect_transients` | `~20` excluded (`snapshot_store.py:52` → `138` etc) | `snapshot_store.py:52 store=Store()` → `138 document.image1_path` exempt |
| **App-wide generation** (audit `test_no_tab_to_tab_service.py:57` style) `INTERMEDIATE` from `ViewportState.__slots__` `src/core/store_viewport.py:259` + `SessionData.__slots__` `122` + `viewport/document/state_slots` → `{"viewport","session_data","image_state","render_cache","document","state_slots","view_state","interaction_state","geometry_state","render_config"}` `test_no_direct_store_mutation.py:31` | `60` (after narrow 78 fixed, new coverage) | `use_cases/navigation.py:12 view_state.showing_single_image_mode`, `multi_compare/scene/store.py:607 state_slots[self._SLOT]` |

Full breakdown (60 app-wide, after Phases 1-4 narrow fixes):

| Bucket | Files | Count | Hot lines |
|---|---|---|---|
| `view_state` / `interaction_state` / `geometry_state` | `canvas/features/divider/commands/registry.py:145`, `magnifier/commands/interaction.py:22`, `presenters/toolbar/actions.py:55`, `plan_applicator.py:261` `vp.geometry_state`, `navigation.py:24` | ~22 | `registry.py:145 is_dragging_split_line`, `actions.py:55 highlighted_overlay_element`, `apply.py:178 active_overlay_screen_center` |
| `render_config` | `navigation.py:83`, `transient_interpolation.py:105`, `session_persistence.py:218` `viewport.render_config` | ~6 | `navigation.py:83 interpolation_method`, `218 viewport.render_config =` |
| `document` / `state_slots` (remaining) | `multi_compare/scene/store.py:607`, `document_store_ops.py:118` `live_doc.image_list1` (post-fix residue), `simple_adapter.py:66` | ~8 | `multi_compare 607 state_slots[self._SLOT]` |
| `view_state` canvas_widget_state | `magnifier/persistence.py:189`, `feature_state.py:52` `view_state.canvas_widget_state` | ~4 | — |
| Other `viewport` / `settings` not covered (settings/workspace excluded to avoid `self.workspace` false positive `src/core/main_controller.py:47`) | — | — | — |

### 2.2 Why `image_state.image1 = u1` breaks Redux

- Skips `dispatcher.py:187 with _lock`, `239 _action_history`, `243 _UNDOABLE_TYPES`/undo snapshot, `278 subscriber(action)`, `286 emit_state_change(scope)` (`STORE.md:159` All state changes go through Dispatcher).
- Mutates live `ViewportState` (`store_viewport.py:122 SessionData` opaque) in place → `dispatcher.py:214` session re-point `active_session.viewport = store.viewport` not updated; `workspace` switch restores old object (`store.py:52 document/viewport` proxy to `get_active_workspace_session`).
- No `dispatch.begin/end` in `tracing/instrumentation.py:38` → `trace.jsonl` orphan `store.emit_state` (`TRACING.md:30`).
- Caught by `test_reducer_purity_full.py:151` only inside reducer, not application code.

### 2.3 Existing sanctioned pattern

`_session_controller.py:188` `dispatcher.dispatch(SetUnificationInProgressAction(False))` → `ImageSessionReducer` `reducers.py:50` `replace(image_state, image1=action.image)` → `dispatcher.py:208 store.viewport = new_store.viewport` + `237 active_session.viewport`.

## 3. Design

**Dogma architecture (AST, no runtime):**

- `tests/contracts/test_no_direct_store_mutation.py:1` `test_no_direct_store_mutation` — `_get_chain` returns `[a,b,c]` for `a.b.c`, `_collect_transients` tracks `Store()/SessionData()/DocumentModel` construction + transitive `document = store.get_session_state_slot(...)`, `_direct_store_mutations` flags any `Assign/AnnAssign/AugAssign` where chain contains `INTERMEDIATE` and `chain[0]` not in transients and file not in `EXEMPT`. One failure lists `78 hits` with `file:line — chain = ...`.
- Keeps `test_viewport_state_slots.py:83` slotted check as sibling; this dogma subsumes the deeper chains.
- Skill `imgsli-devtools` for verification: `./launcher.sh test tests/contracts -q` (fast dogma), `QT_QPA_PLATFORM=offscreen pytest -q tests/<area>` (focused), `IMGSLI_TRACE=1 ./launcher.sh run --debug` → `~/.local/share/ImproveImgSLI/trace.jsonl` `jq '.payload.diff'` must show `viewport.session_data` diff per fix.

**Mutation fix pattern (one per site, no new enum):**

```python
# before: src/tabs/image_compare/use_cases/loading.py:639
image_state.image1 = u1
# after:
from tabs.image_compare.state.actions import SetImageSessionImageAction
store.get_dispatcher().dispatch(SetImageSessionImageAction(slot=1, image=u1), scope="viewport")
# or document path: SetCurrentIndexAction / SetFullResImageAction already exist — reuse
```

For `render_cache.unification_in_progress` use existing `SetUnificationInProgressAction`/`SetPendingUnificationPathsAction` (already dispatched in `_session_controller.py:188`). For `psnr/ssim` use `SetPsnrValueAction`/`SetSsimValueAction` (`state/reducers.py:60`). For `cached_diff_image` use `SetCachedDiffImageAction` (or add if missing, but prefer existing `invalidate` path).

**Transient exemption (data-flow, not allowlist):** any `store = Store(); store.create_workspace_session(...)` plus `document = store.get_session_state_slot("document")` chains where root in transients → exempt. Live `self.store.viewport...` in same file (`snapshot_render_plan_builder.py:352`) still flagged because `self` not in transients.

## 4. Steps — breaking allowed, one app not IDE

### Phase 0 — Preflight (read-only, green baseline) — Done 2026-08-29

Files: `tests/contracts/test_no_direct_store_mutation.py` (new), `tests/contracts/_framework.py:23`

1. Land dogma file as above, exempting `Store`/`Reducer` impl + transient flow.
2. Run `PYTHONDONTWRITEBYTECODE=1 QT_QPA_PLATFORM=offscreen pytest tests/contracts/test_no_direct_store_mutation.py -q` → expect `1 failed, 78 hits` (record table in §2.1).
3. Run `pytest tests/contracts -q` and `mypy` baseline — other 78 + existing contracts green except this new failure (expected).

### Phase 1 — Fix hot-path unify/render (`use_cases/loading.py`) — P0 race

Files: `src/tabs/image_compare/use_cases/loading.py:42`, `src/tabs/image_compare/state/actions.py`, `reducers.py:50`

1. Replace `render_cache.cached_diff_image = None` `42` / `unification_in_progress =` `62,165,188,262,300,553` / `pending_unification_paths =` with `dispatch(SetUnificationInProgressAction / SetPendingUnificationPathsAction / SetCachedDiffImageAction)`.
2. Replace `309 image_state.image1/2 = None` and `639 image_state.image1/2 = u1/u2` in `on_unified_images_ready:599` with `SetImageSessionImageAction(slot=1/2)`.
3. Replace `85,89 document.current_index1 =` etc (6 hits) with existing `SetCurrentIndexAction` (check `DocumentReducer` `reducer.py:27`).
4. Verify: `pytest tests/contracts/test_no_direct_store_mutation.py -q` hits `78→~56`, `python -m pytest tests/runtime/test_reducer_purity_full.py -q`, `IMGSLI_TRACE=1` shows `dispatch` for unify.

### Phase 2 — Fix document slot direct writes (`document_store_ops.py`, `playlist_components`)

Files: `src/tabs/image_compare/services/document_store_ops.py:32`, `services/playlist_components/list_operations.py:41`, `common.py:21`

1. Remove fallback `else: image_state.image1 = None` `37` / `store.viewport... =` `74` — require dispatcher (early bootstrap already has `Store.create_workspace_session` before these calls; assert instead of fallback).
2. Swap `vp.session_data.image_state.image1, image2 =` `101` and `list_operations.py:57 self.store.viewport...` → two `SetImageSessionImageAction` dispatches inside `store.batch_changes()` to keep atomic swap.
3. `common.py:21 document.current_index1` → `SetCurrentIndexAction`.
4. Verify: `unified_list_picker/common.py:179` `document.list1` — check if transient `document = store.get_session_state_slot` derived from live `store` (not `Store()`) → fix via `SetImageListAction` or document reducer branch.

### Phase 3 — Fix analysis / metrics / diff cache

Files: `src/tabs/image_compare/services/analysis/metrics.py:109`, `cached_diff.py:23`, `magnifier/workers/diff_cache.py:83`

1. `metrics.py:109 psnr/ssim` → `SetPsnrValueAction`/`SetSsimValueAction` (already in `reducers.py:60`), keep staleness token `_metrics_request_id:18` guard.
2. `cached_diff.py:23,119` and `diff_cache.py:83` `cached_diff_image` → `SetCachedDiffImageAction` + `emit_state_change("viewport")` (already distinct from `persistence` transient).
3. `snapshot_render_plan_builder.py:352 self.store.viewport...cached_diff_image` → dispatch (live, not transient `97`).
4. Verify: `tests/render -q` GPU fallback still `1.0` coverage, `tests/plugins -q` metrics still green.

### Phase 4 — Fix persistence pre-dispatch restores

Files: `src/tabs/image_compare/session_persistence.py:101`, `ui/settings_persistence.py:20`, `use_cases/persistence.py:222`

1. `image_state.auto_calculate_psnr` loads from `get_setting` — dispatch `SetAutoCalculatePsnrAction` after `Store` has dispatcher (defer via `QTimer.singleShot(0)` if called during bootstrap before `get_dispatcher`, per `dispatcher.py:118` no-sync-dispatch rule).
2. `session.document =` `222` → `SetDocumentAction` or `store.set_session_state_slot("document", ...)` inside `batch_changes` with `emit_state_change("document")`.
3. Verify: `tests/runtime/test_settings_full_pass.py -q` still hermetic (`plan_test_suite_revision.md` hermetic fixture), no real `~/.config` write.

### Phase 5 — App-wide extension (generation, 60 hits) — In progress

Files: `tests/contracts/test_no_direct_store_mutation.py:31` (`_build_intermediate` from `ViewportState.__slots__` + `state_slots`, `_build_exempt` via `tabs` discovery), `src/tabs/multi_compare/scene/store.py:607`, `src/tabs/image_compare/use_cases/navigation.py:12`

1. Generation: replace hard-coded `INTERMEDIATE` with `_build_intermediate()` (10 names) and `EXEMPT` with `_build_exempt()` (like `test_no_tab_to_tab_service.py:57` dynamic `_known_tabs`), handle `Subscript` `state_slots[...]`.
2. Re-run `pytest tests/contracts/test_no_direct_store_mutation.py -q` → `60 hits` app-wide (new `view_state`/`geometry_state`/`render_config`/`state_slots`).

### Phase 6 — Fix remaining app-wide buckets (60 hits) — In progress

Buckets for 4 parallel subagents (all in SINGLE message per `parallel-execution` skill, `imgsli-devtools` for verification):

* **A `view_state/interaction_state`** — `canvas/features/divider/commands/registry.py:145` `is_dragging_split_line` → `SetDraggingSplitLineAction`, `presenters/toolbar/actions.py:55` `highlighted_overlay_element` → `SetHighlightedOverlayElementAction`, `lifecycle.py:121` `is_interactive_mode` etc — via existing `ViewStateReducer`/`InteractionStateReducer` `src/core/state_management/reducers.py:106`.
* **B `geometry_state/render_config`** — `plan_applicator.py:261` `vp.geometry_state.pixmap_width` → `SetGeometryAction`/`SyncGeometryState`, `navigation.py:83`/`transient_interpolation.py:105` `render_config.interpolation_method` → `SetInterpolationMethodAction` `src/tabs/image_compare/state/reducers.py:60`, `session_persistence.py:218` `viewport.render_config =` → `replace` via dispatch.
* **C `state_slots/document` multi_compare** — `multi_compare/scene/store.py:607` `session.state_slots[self._SLOT] =` → `store.set_session_state_slot("multi_compare.state", ..., emit_scope="viewport")` / `Dispatcher.dispatch` with slot reducer `src/tabs/multi_compare/bootstrap_reducers.py:19`, `document_store_ops.py:118` residue `live_doc.image_list1` etc via `DocumentModel` replace.
* **D `canvas_widget_state` + misc** — `magnifier/persistence.py:189` `view_state.canvas_widget_state` + `state/snapshot_store.py:107` `runtime_cache` already exempt, `values.py:455` `interpolated.render_config` — verify transient vs live, fix live with `UpdateCanvasFeatureState` + `emit_viewport_change`.

### Phase 7 — Close dogma and docs

Files: `docs/dev/STORE.md:157`, `docs/dev/CONTRACTS.md`, `docs/dev/TODO.md`, `src/devtools/docs_link_graph.py`

1. Dogma green app-wide: `pytest tests/contracts -q` `0 failed` (60→0).
2. Update `STORE.md:157` invariants — add example of forbidden `view_state.canvas_widget_state =` vs sanctioned `dispatch(SetViewStateAction)` and `state_slots` Subscript pattern.
3. Run `python src/devtools/docs_link_graph.py --write-index` → `tests/devtools/test_docs_link_graph.py -q` + `file_meta.py --write-registry`.
4. Full suite `QT_QPA_PLATFORM=offscreen pytest -q` + contracts quick job — matches `plan_test_suite_revision.md:201` CI gates.

## 5. Risks

- **Bootstrap before dispatcher** (`session_persistence.py:101` runs before `get_dispatcher` wired `bootstrap.py`) — fix must defer via `QTimer.singleShot(0)` not fallback direct (same deadlock contract `dispatcher.py:118`).
- **Deadlock via synchronous dispatch inside `on_change`** (`_session_controller.py:108` already uses `QTimer.singleShot(0, _resync)`) — new dispatches from `on_unified_images_ready:599` run on GUI thread via `GenericWorker` result signal, safe; never call `dispatch` while holding `dispatcher._lock`.
- **Phase 1 swap atomicity** — two `dispatch` for `image1, image2` swap must be `batch_changes()` (STORE.md:46) to avoid intermediate `Store` where only one side swapped (would re-trigger `left-on-right` fallback guard `renderer.py:383`).
- **Transient false positive** — exempt by `Store()`-flow, not file list, so live `self.store` in same file not hidden (validated `snapshot_render_plan_builder.py:352` stays flagged).

## 6. Progress log

| Step | Date | Result |
|---|---|---|
| 0 | 2026-08-29 | Dogma landed `tests/contracts/test_no_direct_store_mutation.py:1` — 78 hits (narrow), baseline `pytest tests/contracts/test_no_direct_store_mutation.py -q` 1 failed (table §2.1). 4 parallel `explore` subagents mapped violations. |
| 1 | 2026-08-29 | Phase 1 `use_cases/loading.py:42` — replaced 22 hits with `SetUnificationInProgressAction`/`SetImageSessionImageAction`/`SetCurrentIndexAction` via `batch_changes`. `78→51`, `loading.py` 0 hits. |
| 2 | 2026-08-29 | Phase 2 `document_store_ops.py:32` + `playlist_components` — removed fallback direct, atomic `batch_changes` dispatches. `78→41` → `0` for bucket. |
| 3 | 2026-08-29 | Phase 3 `metrics.py:109`/`cached_diff.py:23`/`diff_cache.py:83`/`snapshot_render_plan_builder.py:352` — `SetPsnr/Ssim/CachedDiffImageAction` with staleness guards. 4 files 0 hits. |
| 4 | 2026-08-29 | Phase 4 `session_persistence.py:101`/`settings_persistence.py:20`/`persistence.py:222`/`unified_list_picker/common.py:179` — `SetAutoCalculate*Action`/`set_session_state_slot` with `QTimer.singleShot(0)` defer. 0 hits narrow. |
| 5 | 2026-08-29 | Narrow dogma green `tests/contracts -q` 1547 passed, `file_size_registry.json` regenerated, `docs_link_graph.py --write-index` 0 broken. 4 parallel `general` subagents (SINGLE message per `parallel-execution` skill). |
| 6 | 2026-08-29 | App-wide generation: audit subagent found narrow misses `view_state`/`geometry_state`/`render_config`/`multi_compare.state` (like `test_no_tab_to_tab_service.py:57` dynamic). Rewrote `test_no_direct_store_mutation.py:31` `_build_intermediate` from `ViewportState.__slots__` + `_build_exempt` via `tabs` discovery, added `Subscript` for `state_slots`. New baseline `60 hits` app-wide. |
| 7 | 2026-08-29 | Phase 6 buckets defined (A `view_state/interaction_state`, B `geometry_state/render_config`, C `state_slots`, D `canvas_widget_state`) for 4 parallel `general` subagents — firing now. |

## 7. Deviations from the plan (deliberate, recorded)

- N/A yet.

## 8. References

- This session: `src/tabs/image_compare/use_cases/loading.py:639`, `services/document_store_ops.py:37`, `services/analysis/metrics.py:109`, `tests/contracts/test_no_direct_store_mutation.py:1`, `tests/contracts/test_viewport_state_slots.py:40`, `src/core/state_management/dispatcher.py:118`, `src/core/store_viewport.py:122`, `src/tabs/image_compare/state/reducers.py:50`
- Prior: `improve-imgsli-internal-docs/docs/legacy/plan_test_suite_revision.md:1` (template, phases, hermeticity, ownership map), `improve-imgsli-internal-docs/docs/legacy/plan_app_wide_tokenization.md:1` (inventory table, 386 QColor scan pattern), `improve-imgsli-internal-docs/docs/legacy/rendering/tile-array-atlas-plan.md:1` (phased findings, status flips)
- Docs: `docs/dev/STORE.md:3` (Action→Dispatcher→RootReducer→Store), `docs/dev/CONTRACTS.md:303` (contract dogmas), `docs/dev/ARCHITECTURE.md:216` (State Model), `docs/dev/TRACING.md:30` (dispatch chain), `docs/dev/TESTING.md:22` (contract vs runtime)
- Skills: `.cursor/skills/imgsli-devtools/SKILL.md:1` (tool table, workflow 1-4), `.cursor/skills/sli-ui-toolkit-docs-first/SKILL.md:1` (N/A, Store only)
- Investigations: `improve-imgsli-internal-docs/docs/dev/investigations/preview-display-session-2026-08-29.md` (preview race), `docs/dev/rendering/tile-rendering-system.md:381` (StoreLease), `docs/dev/ARCHITECTURE.md:228` (__slots__ guard)

