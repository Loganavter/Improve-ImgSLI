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
Still open:

- Inverse undo/redo reducers and hotkeys (`Dispatcher.bind_history_for_session`
  stores append-only history in `state_slots["action_history"]` only).
- `session_picker` has nothing to serialize (inherits no-op default).
- Longer-term: bind `MultiCompareWidget` purely to the active session's
  `state_slots["multi_compare.state"]` so undo, serialization, and observers
  share one path (today the widget embeds a `MultiCompareStore` swapped via
  `replace_state`).

## P2 - Preview-at-load via QImage (skip transient PIL buffer)

Status: `Design needed`

Area: `shared/image_processing/progressive_loader.py`, image load workers

Optional: decode preview with `QImageReader` + `setScaledSize` (or
equivalent) and keep preview as `QImage` until the canvas path consumes it,
avoiding an intermediate PIL RGBA buffer on the hot load→first-paint path.
Not required for correctness — current PIL-preview design is intentional and
documented in
[tile-rendering-system.md § Preview-at-load tier](rendering/tile-rendering-system.md#preview-at-load-tier).

**Before coding:** audit format coverage (JXL, clipboard paste, auto-crop),
where preview is converted back to PIL for unify/display-cache, and whether
`pick_first_real` needs a third tier or a small adapter.

Related: preview tier contract tests in
`tests/contracts/test_preview_tier_contract.py`.

## P2 - Reduce PIL from universal currency to one decode backend among several

Status: `Open`

Area: `shared/image_processing/` (`pixel_source.py`, `tiled_pixel_store.py`,
`progressive_loader.py`, `pixel_ops/`), `shared/analysis/`, and effectively
every consumer of `PIL.Image` across the pixel pipeline (~80 files import
`PIL` directly today).

`pyvips`/`imagecodecs`-based true streaming decode already exists (see
[tile-rendering-system.md § Strip spill on load](rendering/tile-rendering-system.md#host-side-memory-bounding)),
but only as an opportunistic fallback gated on `pyvips` happening to be
installed — and currently, `pyvips` isn't actually declared as a
dependency in any packaging target (AUR `depends`, Flatpak
`python3-modules.json`, or documented as an `optdepends`/optional feature
anywhere), so the streaming path is effectively dead in every shipped
build today; every real user still hits the PIL/imagecodecs full-frame-materialize
path and the `65536px` sanity bound it implies (see AGENTS.md "Known
Constraints").

Longer-term idea (not urgent, no current user complaint): make
pyvips/imagecodecs-based streaming decode the primary path instead of an
optional bonus, with `PIL.Image` demoted to one interchangeable decode
backend rather than the pipeline's universal in-memory currency type. This
would let the `65536px` limit become a soft/removable bound structurally,
not just something bypassed when a specific optional dependency happens to
be present. Numpy stays regardless — it's load-bearing for
`TiledPixelStore`'s memmap storage and is a transitive dependency of
scikit-image/scipy either way, so there's no equivalent win from touching it.

**Before coding:** decide whether `pyvips` becomes a hard dependency
(declared everywhere, closing the current packaging gap) or stays optional
with a clearly documented feature-flag story; this is a large-surface-area
rewrite (every `PixelSource`/export/analysis call site), so it needs its own
design pass, not an incidental patch.

## P2 - UI scale factor (interface scaling)

Status: `Design needed`

Area: `shared_toolkit/`, external `sli-ui-toolkit` (theming/layout), settings UI

Planned: a user-facing interface scale setting (independent of the OS/Qt
display scale factor), so the app chrome — toolbar/panel sizes, fonts, icons,
spacing — can be scaled up/down without relying on system DPI settings.
No design doc yet: needs a pass on where scale is read (`ThemeManager`?
`shared_toolkit` layout constants? per-widget?), whether it interacts with
existing HiDPI/`devicePixelRatio` handling, and how canvas-px (see
[rendering/coordinate-systems.md](rendering/coordinate-systems.md)) stays
independent of chrome scale.

## P2 - UI inspector: major update

Status: `Open`

Area: `src/devtools/ui_inspector/`, [UI_INSPECTOR.md](./UI_INSPECTOR.md)

Planned larger pass on the UI inspector beyond the current QWidget
palette/theme-token/QSS-candidate feature set — see
[UI_INSPECTOR.md § Future Canvas Inspector](./UI_INSPECTOR.md#future-canvas-inspector)
for the previously-scoped direction (canvas/render-pass diagnostics: QRhi
passes, feature payloads, store-backed colors around the cursor, not just
QWidget tree). Scope of the update itself not yet broken down — needs a
design pass before implementation.

## P2 - Action palette / Help follow-ups

Status: `Open`

Host discovery MVP and hierarchical Help are live — see [ACTIONS.md](./ACTIONS.md),
[HELP_SYSTEM.md](./HELP_SYSTEM.md).

Still open:

- embedded `video_url` / `learn_more_url` on actions;
- F1 → topic page without opening the palette;
- optional Help menu demotion vs Find Action;
- real Help screenshots;
- optional `:::tip` / richer definition-list blocks in the toolkit subset.

Primary UX remains **action discovery** (Find Action / command palette). Full
manual reading is secondary; no PDF / CMS / in-app browser.
