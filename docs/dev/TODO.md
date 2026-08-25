# Development TODO

Shared engineering backlog for work that is too large for incidental bug-fix
patches. Completed work belongs in the living architecture docs (THEMING,
STORE, HELP_SYSTEM, tile-rendering-system, ACTIONS, …), not here — entries
below get pruned once `Done`, not left to accumulate as a changelog.

Priority markers:

- `P0` - blocks a critical workflow or causes data loss/crashes.
- `P1` - important product limitation or visible correctness issue.
- `P2` - infrastructure debt that should be planned, but is not urgent.
- `P3` - cleanup, documentation, or quality-of-life work.

Status markers:

- `Open` - not started.
- `Design needed` - needs an architecture pass before implementation.
- `Blocked` - waiting on another task or external constraint.
- `In progress` - actively being worked on.

## P1 - Cross-tab failure surfacing & export correctness (review 2026-08-25)

Status: `Open`

Area: `src/tabs/multi_compare/use_cases/loading.py`,
`src/tabs/image_compare/plugins/video_editor/services/video_export/service.py`,
`src/ui/actions/widget_pulse.py`

Findings from the cross-module review
([investigations/cross-module-review-2026-08-25.md](./investigations/cross-module-review-2026-08-25.md),
sections A1–A3, C9):

- **MC load failures are log-only** — IC surfaces failed image
  loads/full-res decodes via `CoreErrorOccurredEvent`; Multi Compare only
  logs and silently skips (`use_cases/loading.py:122-124, 291-293`), so a
  dropped corrupt file just never appears. Route through the existing
  event/toast plumbing like IC does.
- **Video export can report false success** — the render-loop exception in
  `video_export/service.py:469-471` is swallowed without re-raise; a
  partially written file may pass the returncode check. Re-raise into the
  existing `export_flow.on_error` path.
- **`.jxl` drag&drop divergence** — IC accepts `.jxl`, MC rejects it
  (`ic/use_cases/drag_drop.py:12` vs `mc/ui/drag_drop.py:14`). One shared
  accepted-formats constant.
- Remove committed unconditional `print()` from `ui/actions/widget_pulse.py:51,200`
  (paint-path debug noise; LOGGING.md violation).

## P2 - Contract-test blind spots + implied-lookup cleanup (review 2026-08-25)

Status: `Open`

Area: `tests/contracts/`, `src/services/io/project_preview.py`,
`src/ui/actions/platform.py`, `src/__main__.py`, `src/tabs/session_picker/tab.py`,
`src/plugins/settings/pages/keyboard.py`

All ten abstraction findings of the review (sections B/C of the investigation
linked above) are gaps the current contract suite cannot catch:
the implied-lookup test covers only `legacy_tab_widgets`; platform-isolation
matches only `image_compare|image_session` literals and skips
`services/`/`plugins/`; tab-sandbox scans `src/ui/` only.

- Widen scanners first, then fix the call sites they would flag:
  project_preview's canvas duck-typing probe (:91-119 — route through
  `CanvasGeometryProvider`/a preview-canvas service), the topLevelWidgets
  event-bus hunt (`platform.py:83-90`, `connections.py:104-109`),
  `__main__.py:366` `getattr(window, "_menu_controller")`,
  session_picker's registry re-fetch + private-getattr chain
  (`tab.py:59,72-88`), the hardcoded `"session_picker"` branch in
  `plugins/settings/pages/keyboard.py:199`.
- Converge or explicitly sanction the three session-switch state dialects
  (IC snapshot vs MC slot-authoritative vs image_gallery raw read).
- Unify the duplicated toolkit-private `NavigationManager._sections` reach
  in both tabs' `declare_toolbar_navigation` follow-ups (make it return the
  section or wrap in `tabs/host_helpers.py`).
- Document why `contribute_actions` routes via `create_service`
  (active-tab) while its `contribute_*` siblings use `notify_all`.

## P2/P3 - IC↔MC duplication consolidation queue (review 2026-08-25)

Status: `Open`

Low-risk consolidation candidates found by the review (investigation table
B1–B7, B9, B10, B12; QRhi-adjacent B8/B11 stay inside the deferred
canvas-merge scope):

- save-flow coordinator lifecycle (~170 LOC; also resolves the MC
  synchronous-GUI-thread fallback divergence);
- loading-toast lifecycle (~75) and pyramid-build worker (~85; parameterize
  the abort predicates);
- export encoding tail (~55; verify live/export parity per AGENTS.md);
- untested-resolution warning suppress helpers (~40);
- `_img_dims` quartet inside IC (~50), `_RESAMPLE` map ×4, keyboard
  pan/zoom constants, `pixel_cache_registry.lookup` snippet ×4;
- delete IC `_generate_unique_filepath` in favor of shared
  `next_available_path`;
- logging normalization sweep (`exc_info=True`, one toast-failure style,
  bootstrap silent-swallow audit);
- dead-code removals: unreferenced `multi_compare/plugins/export/dialog.py`
  (~600 LOC) and zero-importer `ui/widgets/__init__.py` re-export facade.

Renderer-unification Phase 4 (`drop_covered_*`) is effectively complete —
primitive lives in `shared/rendering/tile_coverage.py`; close rather than
schedule further work.

## P3 - CODE_PATTERNS.md: add the "who owns the state" axis

Status: `Open`

The thin-owner + `use_cases/` pattern is declared only as a remedy for
mixed-concern growth; it lacks a decision rule for concerns that own their
own state/lifecycle. Review follow-up (2026-08-25): the largest IC↔MC
duplicates found (save-flow ~170 LOC, loading-toast ~75, pyramid-build
~85) are exactly flow-shaped concerns written as *functions over different
owners* in both tabs, which made shared extraction non-mechanical — while
toast already grew a state-owning `SaveToastMixin` ad hoc. Proposed doc
addition: if a concern owns its own state/lifecycle → small collaborator
object (parameterizable, shareable across tabs); widget-glue whose state
genuinely lives on the owner → keep the use_cases function shape. Also
record the observed inconsistent placement (IC drag&drop under `use_cases/`,
MC under `ui/`) and either converge it or sanction both homes.

## P2 - Session-state follow-ups

Area: workspace sessions, tab lifecycle, project I/O

Related: [tabs/session-lifecycle.md](./tabs/session-lifecycle.md),
[EVENT_BUS.md](./EVENT_BUS.md)

Infrastructure for sessions, `state_slots`, activation events, project
serialize/deserialize hooks, and duplicate-as-new-session is in place.

Done (2026-08-10): **undo/redo** — reference-snapshot stacks per session in
`state_slots["undo_stack"]`/`["redo_stack"]`, `Dispatcher.undo()/redo()`,
Ctrl+Z / Ctrl+Shift+Z / Ctrl+Y, palette entries `platform.undo`/`platform.redo`
(image_compare scope, loading-blocked, coalesces continuous gestures).

Done (2026-08-10): **MultiCompare bound to `state_slots["multi_compare.state"]`**
— MC actions flow through the core `Dispatcher` (slot reducer in
`multi_compare/bootstrap_reducers.py`), `MultiCompareStore` is a facade over
the core Dispatcher + active session slot, the tab's snapshot/restore mirroring
is removed, and undo/redo (Ctrl+Z / CSD buttons) now covers Multi Compare too
(`RemoveSlot`/`Clear` defer closing removed stores so undo restores a live
store). See `src/tabs/multi_compare/docs/state-unification-plan.md`.

Still open:

- Nothing in this area — see the resolved entries below.

Resolved (2026-08-13): **undo of image browsing** — the combobox index
change now dispatches `SET_CURRENT_INDEX` (previously a direct document
mutation), and the tab re-syncs the displayed image on the "document" scope
emit that undo/redo produces (`resync_current_image_slots`, path+reload —
the restored snapshot's pixels can reference the closed `TiledPixelStore`).
Undo of image *load/replace* stays deliberately excluded: loading closes the
replaced store, so a reference snapshot would hold a closed store (recorded
in `dispatcher.py` `_UNDOABLE_TYPES`).

Resolved (2026-08-13): **grouping non-continuous rapid same-type actions** —
`Dispatcher` merges same-type undo entries dispatched within
`_RAPID_ACTION_GROUP_MS` (400 ms, platform double-click convention) into one
step (the snapshot `after` moves forward, `before` stays — the pre-burst
state). Continuous gestures keep their unlimited-time coalescing
(`_COALESCE_TYPES`).

## P2 - UI scale factor (interface scaling)

Status: `Done` (`UiScale` in sli-ui-toolkit, settings page "Interface Scale"
0.5–2.5, live apply, full px sweep + QSS pass)

Area: `shared_toolkit/`, external `sli-ui-toolkit` (theming/layout), settings UI

Planned: a user-facing interface scale setting (independent of the OS/Qt
display scale factor), so the app chrome — toolbar/panel sizes, fonts, icons,
spacing — can be scaled up/down without relying on system DPI settings.

Shipped: settings page "Interface Scale" (slider 50–250 → factor 0.5–2.5,
applies live) driven by the toolkit `UiScale` singleton (`scale_changed`
fan-out, `scaled_px`); one atomic live pass freezes top-level paints,
re-pushes QSS with every `Npx` literal scaled (`ThemeManager._scale_qss_px`)
and re-syncs fonts (`UiFont.sync_from_application`); the factor is applied
at startup before any widget is built. Canvas-px stays independent of the
chrome scale: no `UiScale` use in canvas/rendering paths, the scale is
absorbed by `sr` (see
[rendering/coordinate-systems.md](rendering/coordinate-systems.md)).
Design notes: `improve-imgsli-internal-docs/docs/legacy/plan_ui_unification.md`
(locked decisions, HiDPI/DPR orthogonality, canvas independence) and toolkit
`docs/dev/DESIGN_LANGUAGE.md` (design px at factor 1.0, `UiScale` contract).

## P2 - UI inspector: major update

Status: `Done` (2026-08-13).

The inspector is now toolkit-level (`sli_ui_toolkit/ui/inspector/`):
widgets self-describe via co-located `inspect_spec` class attributes
(config auto-derived from `__init__`, curated state with labels), the
DevTools-style `InspectorWindow` (Object/Config/State/Regions/Layers/Theme/
Layout/Constructor/Code/Docs pages, per-region overlay, live token capture
through the `get_color` funnel, dead-QSS-selector analysis in the Code
page) lives in the toolkit, and
the app keeps a thin wiring layer (installer, Native diagnostics, Dump
layout, app-family specs). Canvas/render-pass diagnostics remain a separate
future concern (see UI_INSPECTOR.md).

## P2 - Action palette / Help follow-ups

Status: `Open`

Host discovery MVP and hierarchical Help are live — see [ACTIONS.md](./ACTIONS.md),
[HELP_SYSTEM.md](./HELP_SYSTEM.md).

Still open:

- embedded `video_url` / `learn_more_url` on actions;
- F1 → topic page without opening the palette;
- optional `:::tip` / richer definition-list blocks in the toolkit subset.

Resolved / decided:
- real Help screenshots — done (all figures real: `check_help_figures.py`
  reports 19 ready / 0 stub);
- optional Help menu demotion vs Find Action — decided against: current
  title-bar Help menu is fine, Find Action can reach help pages already, so
  nothing is duplicated.

Primary UX remains **action discovery** (Find Action / command palette). Full
manual reading is secondary; no PDF / CMS / in-app browser.
## P3 - Code mass reduction (all sprints resolved)

Status: `Done` (2026-08-17; deferred items tracked in the plan doc)

Plan and status: [CODE_MASS_REDUCTION.md](./CODE_MASS_REDUCTION.md) —
grounded in the 2026-08-17 audit. All sprints executed and resolved: total
**~2 700 LOC deleted** (net ≈ −2 400 with the plan doc and test rewrites),
contract suite 1391–1397 passed / 1 skipped throughout.

Done (2026-08-17): **Sprint 1 — 41 files removed, ~1 955 LOC deleted.**
Byte-identical duplicates (`magnifier/commands/registry.py`,
`palette/host.py`, `base_plugin.py`), dead GLSL containers
(`magnifier/shaders/`, `canvas/shader_sources/`,
`multi_compare/shaders/__init__.py`), 14 orphan modules, 12 compat shims
(test imports rewritten to real modules), `shared/regions.py` merged into
`shared/image_processing/regions.py`, unused `chevron-down.svg`. Contracts:
1397 passed / 1 skipped. Doc-link side effect fixed
(`tile-rendering-system.md` → `tiled_pixel_store.py`).

Done (2026-08-17, same session): **pull-forward from Sprint 2 — ~540 LOC
more.** Write-only registries deleted (`core/plugin_system/contributions.py`
120 + `ui_integration.py` 26: `PluginDefinition`, five registration
dataclasses, `PluginDefinitionRegistry`, `PluginUIRegistry` — zero readers,
bootstrap only validated-then-discarded; plumbing removed from bootstrap /
presenter / ui_manager / features / composer / toolbar connections) and the
dead video-session layer trimmed from `video_editor/model.py` (386 → 112,
`VideoSessionModel`/`VideoDecoderState`/`VideoSourceState`/
`VideoSessionSnapshot` + `test_video_session_model.py` deleted). Contracts
after: 1391 passed / 1 skipped.

Open from Sprint 1 verification (pre-existing on clean HEAD, unrelated to
this work): `test_recent_projects_panel.py::test_shelf_geometry_settles_by_first_drain`
(geometry assert), `::test_window_will_fill_screen_and_prelayout_width_estimate`
(offscreen crash), `tests/runtime/test_list_item_theme_idle.py::test_idle_list_item_matches_panel_background`
(theme palette mismatch), `tests/runtime/test_color_picker_dialog.py::test_fields_row_gaps_stable_and_right_aligned`
(flaky). Fix with their owners before claiming a fully green suite.
