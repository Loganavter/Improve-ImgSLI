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
## P3 - Code mass reduction (sprint 1 in progress)

Status: `In progress`

Plan and status: [CODE_MASS_REDUCTION.md](./CODE_MASS_REDUCTION.md) —
grounded in the 2026-08-17 audit (~5k LOC removable quickly, ~8.5–12.5k with
medium-risk refactors, toolkit +3–7k). Sprint 1 (zero-risk deletions:
byte-identical duplicates, dead GLSL containers, orphan modules, compat
shims) is underway; each deletion is import-grep-verified and followed by
`./launcher.sh test tests/contracts -q`.

Done: none yet.
