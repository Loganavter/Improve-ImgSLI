# Code Mass Reduction

Living plan for reducing the size of the codebase without losing product
capability. Everything here is grounded in the 2026-08-17 read-only audit
(7 parallel agents; AST import graph over 1 059 modules + manual grep
verification of every candidate). Audit reports live outside the repo in
`code-audit-findings/`; this doc is the actionable plan.

Related: [TODO.md](TODO.md) · [CODE_PATTERNS.md](CODE_PATTERNS.md) ·
[CONTRACTS.md](CONTRACTS.md) · [AGENTS.md](../../AGENTS.md)

---

## Why this exists

Improve-ImgSLI is ~147 600 LOC + `sli-ui-toolkit` ~55 800 LOC (~203 000
together). The audit verdict: **~75–85% of `src/` is necessary complexity**
(QRhi canvas pipeline, keyframing/video-export engine, Redux undo/redo,
input routing, plugin logic, test coverage). But ~15–25% is grown scaffolding,
and per-axis reduction potential is:

| Axis | Reducible LOC | Confidence |
|---|---|---|
| Dead code (orphans, dead shaders, shims) | 2 000–2 700 | high |
| Duplication (byte-identical copies, IC↔MC mirrors) | 1 500–2 500 safely | mixed |
| Architecture outside tabs (devtools out, thin managers) | 2 200 fast / 4 500–8 500 total | medium |
| Canvas/magnifier scaffolding | 1 200–2 000 | medium |
| video_editor dead/twilight layer | 600–900 | medium-high |
| Tests (fixture/fake dedup) | 1 300–1 800 | high |
| sli-ui-toolkit (dead + demo-only, lazy imports) | 3 000–7 000 conservative | medium |

Net without double counting: **≈ 4 500–5 500 LOC quickly and safely;
≈ 8 500–12 500 with medium-risk refactors; toolkit another 3–7k.**

## Outcome (2026-08-17)

All sprints executed and resolved. Committed in `36cc4d7e` (Sprint 1) and
`40d4d06e` (Sprint 2 + pull-forwards):

- **Sprint 1 — Done**: 41 files, ~1 955 LOC (duplicates, dead GLSL
  containers, orphans, shims, regions merge) + pulled-forward registries
  (`contributions.py`, `ui_integration.py`) and the dead video-session layer
  (`model.py` 386→112) ≈ 540 LOC more.
- **Sprint 2 — Done**: 20 dead public functions (~205 LOC).
- **Total: ~2 700 LOC deleted** (net ≈ −2 400 accounting for the plan doc
  and test rewrites), every change followed by
  `./launcher.sh test tests/contracts -q` (1391–1397 passed, 1 skipped
  throughout) and a full import sweep.
- **Sprint 3 — Verified, deferred**: the audit's 1 300–1 800 LOC
  "mechanical test dedup" does not hold up — the named duplicates test
  different production code or have different signatures (details in the
  sprint section).
- **Sprint 4 — Evaluated, deferred/blocked**: devtools relocation is a
  packaging lever (not repo LOC), `core/tracing` is a live runtime
  dependency (audit corrected), manager merges cost more churn than the
  ~200 LOC saved, multi_compare consolidation is a long-term design item,
  toolkit work is blocked on the second host (Tkonverter not on disk).

## Principles

1. **Ship nothing that a contract test guards without changing the test
   deliberately.** `tests/contracts/` is the architecture insurance — run
   `./launcher.sh test tests/contracts -q` after every change.
2. **Delete, don't rewrite.** Sprint work is removal of verified-dead code and
   import-path fixes. Structural consolidation (merging layers, unifying
   mutation paths) is separate, higher-risk work tracked below.
3. **Every deletion is preceded by a grep for importers in `src/` and `tests/`
   (including attribute access and lazy `import_module` tables), because the
   runtime uses reflection: plugin discovery, `CanvasFeatureRegistry`,
   `pkgutil` settings pages, `__getattr__` facades.**
4. **Never delete localized content** (i18n/help ×4 languages). The 4 611 LOC
   of translations are product, not waste; only a key registry + lint is
   planned.
5. **No GUI runs during verification** — offscreen pytest only.

## Status legend

`Open` / `In progress` / `Done` / `Blocked` (same convention as
[TODO.md](TODO.md)). Work items are tagged `[S#]` by sprint.

---

## Sprint 1 — Zero-risk deletions (`Done`, 2026-08-17)

Pure removals with **zero importers** (src + tests verified by grep), plus
test-import rewrites. No API changes.

**Result: 41 files deleted / merged, ~1 955 LOC removed, plus the
write-only plugin registries and the dead video-session layer pulled in from
Sprint 2 (~540 LOC more, see below).** Contract suite green (`1397 passed, 1
skipped` at 16:00 commit; `1391 passed, 1 skipped` after the registry/model
removals — the delta is parametrized contract cases over removed shims);
touched families green (`tests/plugins` 279, `image_compare
{contracts,video,runtime,plugins}` 198, `multi_compare`, `session_picker`
except two pre-existing failures — see below). Side effect found by the
doc-link test: `docs/dev/rendering/tile-rendering-system.md` linked to
deleted `pixel_source.py` — reference rewritten to `tiled_pixel_store.py`.

**Pulled forward from Sprint 2 (same session):**
- Write-only registries: `core/plugin_system/contributions.py` (120) and
  `core/plugin_system/ui_integration.py` (26) deleted — `PluginDefinition` +
  all five registration dataclasses + `PluginDefinitionRegistry` had zero
  readers (bootstrap only validated-then-discarded), and `PluginUIRegistry`
  was never populated (`register_action`/`unregister_plugin`/`get_plugin_name`
  uncalled; `get_action` always returned None at its three call sites —
  presenter, ui_manager, toolbar quick-save — now simplified to direct
  fallbacks). Plumbing removed from `bootstrap.py`, `presenter.py`,
  `ui_manager.py`, `features.py`, `composer.py`, `toolbar/connections.py`.
- Dead video-session layer: `video_editor/model.py` trimmed 386 → 112
  (`VideoSessionModel` + `VideoDecoderState` + `VideoSourceState` +
  `VideoSessionSnapshot`, 274 lines, sole user was `test_video_session_model.py`
  — deleted with it). `VideoProjectModel`/`VideoSelectionState`/
  `VideoTimelineState` stay (used by `presenter.py`, `plugin.py`).

Pre-existing failures, NOT caused by this sprint (verified on clean HEAD):
`test_recent_projects_panel.py::test_shelf_geometry_settles_by_first_drain`
(geometry assert) and `::test_window_will_fill_screen_and_prelayout_width_estimate`
(crash under offscreen); `test_list_item_theme_idle.py::test_idle_list_item_matches_panel_background`
(theme palette mismatch); `test_color_picker_dialog.py::test_fields_row_gaps_stable_and_right_aligned`
(flaky). Tracked in `docs/dev/TODO.md` for their owners.

### 1.1 Byte-identical duplicates (~450 LOC)

| File | LOC | Note |
|---|---|---|
| `src/tabs/image_compare/canvas/features/magnifier/commands/registry.py` | 229 | `diff`-identical to `commands/__init__.py`; never imported |
| `src/ui/actions/palette/host.py` | 151 | `diff`-identical to `palette/__init__.py`; never imported |
| `src/core/plugin_system/base_plugin.py` | 70 | `Plugin` lives in `plugin.py`; no importers anywhere |

### 1.2 Dead GLSL source containers (~700 LOC)

Python modules holding GLSL strings that were superseded by `.qsb` files
loaded by path. `qrhi/` subdirectories (shader files only) stay untouched.

- `src/tabs/image_compare/canvas/features/magnifier/shaders/`
  (`__init__.py` 23 + `programs.py` 22 + `sources.py` 463) — runtime loads
  only `qrhi/*.qsb` (arc/border_disk/mag)
- `src/tabs/image_compare/canvas/shader_sources/` (base.py 115 + common.py 7 +
  `__init__.py` 1) — legacy string container; `compile_shaders.py` scans
  `.vert/.frag` files, not this
- `src/tabs/multi_compare/shaders/__init__.py` (49) — unused GLSL strings;
  `qrhi/` stays
- `src/tabs/image_compare/canvas/features/filename_overlay/render/shaders.py`
  (18) — render uses `label_downsample.qsb`

### 1.3 Orphan modules (~450 LOC)

`src/tabs/image_compare/ui/wheel_counter.py` (72) ·
`src/ui/gesture_resolver.py` (72, superseded by
`canvas_infra/scene/gesture_resolver.py`) ·
`src/tabs/image_compare/ui/settings_analysis.py` (59) ·
`src/tabs/image_compare/services/video_timeline_semantics.py` (55) ·
`src/tabs/image_compare/events/drop_hint.py` (49) ·
`src/shared_toolkit/ui/icon_manager.py` (58, stub; real one is
`src/ui/icon_manager.py`) ·
`src/shared/image_processing/pixel_source.py` (32) ·
`src/tabs/image_compare/canvas/features/magnifier/state/runtime_state.py` (27)
· `src/core/interaction_protocols.py` (24) ·
`src/tabs/image_compare/ui/slider_hint_flyout.py` (23) ·
`src/shared_toolkit/ui/managers/flyout_timer_service.py` (7) ·
`src/ui/canvas_infra/rhi/render.py` (3) ·
`src/plugins/export/ui/` (empty package) ·
`src/tabs/image_compare/services/keyframing_adapters/` (empty package)

### 1.4 Compat shims — delete + rewrite test imports (~90 LOC)

Shims re-export from the real module; production has zero importers, a few
tests use the old path. Fix the test import, delete the shim.

| Shim | Tests to rewrite | Real module |
|---|---|---|
| `video_editor/dialog_export.py` (7) | `test_video_editor_fill_color_button.py` ×3 | `dialog/export.py` |
| `video_editor/dialog_persistence.py` (9) | `test_video_editor_preview_settings_contracts.py` ×1 | `dialog/persistence.py` |
| `video_editor/dialog_sections.py` (33) | none | `dialog/sections.py` |
| `video_editor/dialog_runtime.py` (7) | none | `dialog/runtime.py` |
| `video_editor/services/video_export_bounds.py` (9) | contract `test_plugins_isolation.py` (path) | `video_export/bounds.py` |
| `video_editor/services/video_export_images.py` (9) | none | `video_export/images.py` |
| `video_editor/services/video_export_encoding.py` (13) | none | `video_export/encoding.py` |
| `image_compare/services/export_models.py` (7) | none (contract mentions path in message only) | `image_export/models.py` |
| `image_compare/services/export_context_builder.py` (7) | `test_export_diff_support.py` :454, `test_load_unify_ssim_export_lifecycle.py` | `image_export/context_builder.py` |
| `image_compare/services/export_save_flow.py` (7) | `test_toast_and_metrics.py` :20 | `image_export/save_flow.py` |
| `session_picker/recent/shelf_chrome.py` (10) | `test_recent_projects_panel.py` ×2 | `ui/widgets/shelf.py` |
| `image_compare/services/analysis/processing/__init__.py` (28) | none (facade, not in `__getattr__` table) | `shared/analysis/*` |

### 1.5 Unused asset

- `src/resources/assets/icons/{dark,light}/chevron-down.svg` — no references
  in `.py/.qss/.json/.qrc` (94 files checked).

### 1.6 Merge (not delete): `shared/regions.py` (~160 LOC)

`src/shared/regions.py` and `src/shared/image_processing/regions.py` differ
only by `region_for()` (added in the latter, `diff` = 24 lines). Four modules
import `build_uniform_tile_grid` from `shared.regions`:
`src/shared/analysis/{ssim_source,diff_source,differ,edge_detector}.py`.
Rewrite those imports to `shared.image_processing.regions`, delete
`shared/regions.py`, run analysis tests.

### Sprint 1 exit criteria (met)

- `./launcher.sh test tests/contracts -q` green — 1397 passed, 1 skipped
- Offscreen run of touched test families green (see result note above)
- `python src/devtools/docs_link_graph.py` — DOC_INDEX regenerated, 0 broken
  links; `tests/devtools/test_docs_link_graph.py` green
- `git status`: deletions + test import rewrites only

---

## Sprint 2 — Dead symbols inside live modules (`Done`, 2026-08-17)

Verified-unused public functions/classes; remove one file at a time with a
grep before each removal.

**Result: 20 dead public functions removed from 15 modules (~205 LOC),
committed in `40d4d06e`.** Each candidate was grep-verified (0 callers in
`src/`+`tests/`, including attribute access) and removed with an AST-based
per-node edit; a full import sweep of all 867 `src/` modules passed with 0
failures (the first AST pass had a range-slicing bug that ate a live
neighbor function — `resolve_view_px` — caught by `test_tile_constants.py`,
all 15 files restored and re-done per-node). Contract suite: 1391 passed /
1 skipped. Two render-discovery failures
(`test_divider_is_discovered_as_qrhi_render_pass`,
`test_guides_and_capture_are_discovered_as_qrhi_passes`) verified as
pre-existing on the baseline commit (order/environment-dependent discovery),
not caused by this sprint.

Pulled forward and done in the Sprint 1 session: the dead video-session layer
in `video_editor/model.py` (`VideoSessionModel` + `VideoDecoderState` +
`VideoSourceState` + `VideoSessionSnapshot`, 274 lines, + test file) and the
write-only registries (`contributions.py`, `ui_integration.py`) — see the
Sprint 1 result note.

Still open:

- 16 dead public functions (~205 LOC) from `audit-dead-code.md` §2.3:
  `pil_save.attach_comment_metadata`/`flatten_rgba_over_background`/
  `format_needs_alpha_flatten`, `frame_geometry.resolve_*` ×2,
  `runtime.build_canvas_surface_format`/`log_canvas_backend_choice`,
  `render_common.resolve_widget_background`,
  `render_metrics.resolve_image_px`/`resolve_screen_px`,
  `dialog_search.build_results`, `property_access.get_canvas_feature_property_by_id`,
  `interfaces.IRenderPlugin`, `keymap.collect_bindings`,
  `export_tiling.create_offscreen_export_widget`,
  `multi_compare.ui.layout_geometry.nearest_rect_distance_sq`,
  `extension_reducers.clear_extension_reducers`,
  `slot_reducers.get_state_slot_reducer`,
  `first_frame_gate.first_present_settle_count`,
  `help.interpolate.help_figures_path`

### Exit criteria

- `tests/contracts` green; affected unit tests green; no `# noqa` additions.

---

## Sprint 3 — Test mass (`Verified`, 2026-08-17 — deferred)

Audit estimate 1 300–1 800 LOC of "mechanical dedup" did **not survive
verification**; the concrete claims were name-level similarities, not code
identity:

- **Mirrored budget tests**: `image_compare/tests/render/test_realize_tile_plan_budget.py`
  and `multi_compare/tests/render/test_realize_tile_residency_budget.py`
  (note: under `tests/render/`, not `tests/runtime/` as the audit stated) test
  **different production code** (`resources.residency.realize_tile_plan` vs
  `render_pass._realize_tile_residency`) against the same behavior spec —
  intentional parallel coverage, merging would blur two units under test.
- **`test_rmb_surface_is_always_popup` ×2**: same production function
  (`ui/context_menu/manager.rmb_context_menu_surface`) but distinct env
  scenarios (wayland vs win32/version) — ~15 lines, not worth the churn.
- **`_record` closures**: the 3 inspected copies have different signatures
  (`_record(tmp_path, name)`, `_records(tmp_path, n)`, `_record(i)`) — not
  copy-paste.
- **`register_platform_actions` "10 blocks"**: only one contract file
  (`test_action_registry.py`) uses it; not 10 duplicated blocks.
- **`test_settings_in_dialog_search.py` (audit: "empty")**: file does not
  exist.

What remains is real but medium-risk: consolidating the 73 per-file
`_Fake*` families (they are per-subsystem fakes with genuinely different
implementations — each needs identity verification before sharing) and
compressing the settings/find-action clusters by *reducing test
granularity* ("sweep instead of per-property"), which trades failure
isolation for LOC. Decision: **deferred** — test LOC is not shipped, the
coverage these tests provide is the safety net for the whole reduction
program, and the audit's own estimate was inaccurate. Revisit per-subsystem
if a fake family is proven identical.

Sacred: `tests/contracts` AST checks, render family, runtime sessions/project
I/O, devtools tests.

---

## Sprint 4 — Structural consolidation (`Evaluated`, 2026-08-17 — deferred/blocked)

Each item was checked against the code before deciding:

- **`src/devtools/` relocation (1 753) — deferred (packaging lever).** Only
  one production importer exists (`src/__main__.py` under a flag:
  `from devtools.ui_layout_dump import …`) plus `tests/devtools/`; the module
  path `devtools.*` must stay resolvable via `src/` on `sys.path`. The real
  lever is the Flatpak/Windows packaging step (exclude `src/devtools` from
  the copy), not a code move — and it cannot be verified in this repo's
  test scope. No repo-LOC change either way.
- **`core/tracing` (840) — audit correction: do NOT move.** `Tracer` is a
  live runtime dependency: `core/bootstrap.py` installs tracing under env
  flags and three production modules import it
  (`video_editor/presenter_parts/preview.py`,
  `video_editor/services/video_snapshot_rendering.py`,
  `image_compare/services/video_snapshot_rendering/renderer.py`). Only
  `core/tracing/print_tree.py` is a dev-only CLI (`python3 -m
  core.tracing.print_tree`, documented in TRACING.md).
- **Merge thin delegates — deferred.** `SessionManager` has 27 call sites
  across production and is a facade over `Store` + `PluginCoordinator` with
  real metadata logic (`create_session`); `PluginLifecycleManager` is a real
  state machine (initialize/activate/deactivate/shutdown + error capture +
  events), not a pass-through; `ExportController`'s delegating methods are
  the public face used by UI buttons and event handlers and it owns
  recording flags. ~200 LOC of savings do not justify the churn/regression
  surface; the audit overestimated "thinness".
- **`multi_compare/scene`+`canvas` consolidation (5 407) — long-term design
  item.** Parallel reimplementation of the IC canvas; merging render paths
  is the highest-risk item (QRhi fragility). Needs a dedicated design note
  and render-contract test changes before any code.
- **Toolkit (lazy facade imports, dead 1.4k, demo-only widgets) — blocked /
  separate track.** `sli-ui-toolkit` is a separate repo (editable install);
  removing demo-only widgets (calendar, sidebar, sunburst, …) requires the
  second host Tkonverter, which is not on disk — cannot be verified.
  Lazy facade imports are a toolkit-repo change with its own test suite;
  plan as a toolkit project, not an app-repo change.

## Explicitly out of scope (do not touch)

- i18n/help translation packs (product content, 4 611 LOC)
- `tests/contracts` AST dogma — guarded, only deliberate edits
- `canvas/shaders/{base,step1}.*` — contract tests
  (`test_canvas_widget_ownership.py`, `test_windows_shader_bundle.py`) require
  them; revisit consciously with the test authors
- `src/shared/rendering/live_snapshot.py` — contract
  `test_shared_live_snapshot_is_tab_agnostic` requires the delegating stub
- Core keyframing, video export engine, Redux dispatcher, `src/events`
- `docs/legacy/`, `features/_template/` — intentionally preserved
