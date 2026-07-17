# Development TODO

Shared engineering backlog for work that is too large for incidental bug-fix
patches. Completed work belongs in the living architecture docs (THEMING,
STORE, HELP_SYSTEM, tile-rendering-system, ACTIONS, …), not here.

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

- "Save Project" / "Open Project" menu items, `QFileDialog`, or
  `.imgsli-project` file-association wiring.
- Inverse undo/redo reducers and hotkeys (`Dispatcher.bind_history_for_session`
  stores append-only history in `state_slots["action_history"]` only).
- `session_picker` has nothing to serialize (inherits no-op default).
- Longer-term: bind `MultiCompareWidget` purely to the active session's
  `state_slots["multi_compare.state"]` so undo, serialization, and observers
  share one path (today the widget embeds a `MultiCompareStore` swapped via
  `replace_state`).

## P2 - Preview-at-load via QImage (skip transient PIL buffer)

Status: `Open` (design needed)

Area: `shared/image_processing/progressive_loader.py`, image load workers

Today progressive load returns a bounded `PIL.Image` (≤1024 px long edge) into
`document.preview_image*`. That is intentional display-tier storage — small,
transient, discarded once `full_res_image*` lands. Optional follow-up: decode
preview with `QImageReader` + `setScaledSize` (or equivalent) and keep preview
as `QImage` until the canvas path consumes it, avoiding an intermediate PIL
RGBA buffer on the hot load→first-paint path.

**Before coding:** audit format coverage (JXL, clipboard paste, auto-crop),
where preview is converted back to PIL for unify/display-cache, and whether
`pick_first_real` needs a third tier or a small adapter.

Related: preview tier contract tests in
`tests/contracts/test_preview_tier_contract.py`; docs in
[tile-rendering-system.md](rendering/tile-rendering-system.md#preview-at-load-tier).

## P2 - Host vs GPU tile sizes (formalize invariants)

Status: `Open` (design needed)

Area: `core/constants.py`, `shared/rendering/`, IC/MC `TileTextureService`

GEGL keeps **storage tiles** small (default `128×64`; override via
`GEGL_TILE_SIZE`) while graph evaluation / OpenCL paths batch **much larger
processing regions** (e.g. 2048×4096) — storage granularity and compute
granularity are deliberately separate.

Improve-ImgSLI mirrors that split: `PIXEL_TILE_SIZE = 512` (host
`TiledPixelStore`, CPU ops) vs `_LIVE_TILE_EXTENT = 8192` (GPU residency). Do
**not** merge into one constant — unify via shared `tile_constants.py`,
divisibility contract (`GPU % HOST == 0`), and docs; optional follow-up is
asymmetric host tiles (e.g. 512×64) if profiling shows a win.

Related: [tile-rendering-system.md](rendering/tile-rendering-system.md#host-vs-gpu-tile-granularity).

## Done - Strip spill on full-res load

Status: `Done`

`TiledPixelStore.from_pil` / `from_path` write RGBA in `PIXEL_TILE_SIZE`
strips (no second full `HxWx4` copy). IC / video / MC file loads use
`from_path`; `load_full_image` is a materialize escape hatch. Auto-crop uses
a bounded downscale probe. Still not codec ROI streaming; 65536 sanity bound
unchanged.

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
