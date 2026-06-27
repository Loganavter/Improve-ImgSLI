# Development TODO

Shared engineering backlog for work that is too large for incidental bug-fix
patches.

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

## P1 - Large images above 16384 px

Status: `Design needed`

Area: live canvas, export, video snapshots, diff rendering

Related local docs:

- [Multi Compare TODO](../../src/tabs/multi_compare/docs/TODO.md#p2---tiled-large-image-support)

Current state:

- Images above `16384 px` on either side are blocked by software guard.
- The current live renderer maps each loaded image side to one GPU texture.
- Many GPUs/backends report max texture sizes around `16384` or `32768`; the
  app cannot safely assume larger textures exist.

Why this is not just "raise the limit":

- Live canvas, export preview, final image export, and video snapshot rendering
  must stay visually consistent.
- Diff modes (`highlight`, `grayscale`, `edges`, `ssim`) currently depend on
  whole-image or cached diff textures in several paths.
- Magnifier capture/readback assumes a coherent image source and must not show
  seams or stale tiles.
- Full-resolution export cannot render a >16k target as one GPU texture either;
  it needs chunked render/write logic.

Planned direction: tiled rendering.

### Phase 1 - Large image display mode

- Keep full source data CPU-side.
- Build a display/cache image guaranteed to fit QRhi texture limits.
- Allow loading and previewing >16k images with a clear "large image display
  mode" status.
- Keep full-resolution export disabled or routed to existing guarded path until
  tiled export exists.

### Phase 2 - Tiled live renderer

- Split each source image into fixed-size GPU tiles, e.g. `2048` or `4096`.
- Upload only visible tiles plus a small viewport margin.
- Evict tiles outside the visible/cache window.
- Draw one quad per visible tile with UVs derived from image-space coordinates
  so zoom/pan seams do not appear.
- Preserve canvas-px and framebuffer/sr-px separation.

### Phase 3 - Tiled export

- Render output chunks instead of one full-size framebuffer.
- Stitch/write chunks through a streaming or tile-aware image writer.
- Keep export preview, final export, and video snapshot paths using the same
  layout/render plan semantics.

### Phase 4 - Feature parity

- Make diff modes tile-aware, including SSIM/cached diff behavior.
- Make magnifier capture tile-aware.
- Verify overlays, divider/guides, labels, and multi-compare layouts against
  tiled live/export paths.
- Add regression tests for tile seam alignment, visible-tile selection, and
  export/live parity.

Open questions:

- Tile size and cache budget should probably be configurable or backend-derived.
- Need a consistent CPU-source abstraction for PIL/numpy/video frames.
- Need clear UX for operations that are preview-only until tiled export is
  implemented.

## P2 - Session-state infrastructure

Status: `Open`

Area: workspace sessions, tab lifecycle, Redux/store ownership

Related local docs:

- [Multi Compare TODO](../../src/tabs/multi_compare/docs/TODO.md)

Backlog of improvements to the workspace-session machinery
(`core/store_workspace.py`, `domain/workspace.py`, `tabs/contract.py`,
`core/state_management/dispatcher.py`). Not urgent, but captured so the context
is not lost.

Current state as of 2026-06-25:

- `WorkspaceSession` owns `document`, `viewport`, plus generic `state_slots`,
  `resources`, `metadata` dicts.
- `_activate_workspace_session` swaps `store.document` / `store.viewport` to
  point at the active session. Everything that reads via `store.document.*`
  follows the active session transparently.
- Dispatcher (`state_management/dispatcher.py`) re-points the active session's
  `document`/`viewport` after every reducer pass so the session does not keep a
  stale ref. Without this, switching back to an older session restored the
  pre-action state.
- `TabRegistry.activate(session_type)` fires `TabContract.on_activated` on each
  `sync_session_mode`.
- `TabRegistry.deactivate(session_type)` exists, but the main window does not
  call it when switching away.
- `on_session_created` and `on_session_closed` are declared by the contract and
  implemented by Multi Compare, but workspace create/close does not notify tabs
  yet.
- Per-tab snapshot today lives only in `MultiCompareTab._session_states` as a
  singleton dict on the tab instance. It is not canonical and is not visible to
  other systems.

### Wire `on_session_created` / `on_session_closed`

Currently a tab cannot react to its own session lifecycle. The natural hook
points are `store.create_workspace_session` and `store.close_workspace_session`.
Both should iterate the registered `TabRegistry` and notify the owning tab.
Without this, snapshot dicts held on tab instances leak entries forever because
closed sessions never get their state pruned.

### Move multi-compare snapshot onto `state_slots`

`MultiCompareTab` currently keeps `dict[session_id -> MultiCompareState]` on
`self`. Reasonable replacement:

```python
store.set_session_state_slot(
    "multi_compare.scene",
    widget.store.state,
    session_id=session_id,
    emit_scope=None,
)
```

Then read it back on activation. Benefits: visible to other plugins,
auto-cleaned with the session, easier to serialize.

### Persistence / project files

`state_slots` and `resources` hold runtime objects such as numpy arrays and GL
handles. No JSON/pickle layer exists. For "open project" or "recent session" we
need either:

- per-tab serializers registered on `TabContract`, or
- a `SessionBlueprint.snapshot/restore` pair invoked by a project I/O service.

Heavy refs such as images likely need offload-to-disk strategy with a manifest.

### Per-session undo/redo

`Dispatcher._action_history` is global. To support "undo within tab", the
history would need to be sharded per active session and stored on the session
itself, likely as a new `state_slots["action_history"]` or a dedicated
`WorkspaceSession.history` field. Switching tabs would swap which history is
"current".

### Duplicate-as-new-session

`create_workspace_session` already deep-copies `canvas_widget_state`. A full
"Duplicate tab" command needs:

- deep-copy `document` and decide whether image refs are shared or cloned,
- deep-copy `viewport.session_data`,
- copy `state_slots`/`resources` opt-in per blueprint because some entries are
  intentionally session-local, such as thread pools and GL textures.

This probably belongs on `SessionBlueprint` as a `clone(session) -> session`
hook.

### Multi-compare per-session: real model

Today the `MultiCompareWidget` has a single embedded `MultiCompareStore` that
is swapped via `replace_state`. Long-term it would be cleaner to:

- keep the widget purely visual,
- bind it to whatever `MultiCompareState` lives on the active session's
  `state_slots`,
- have all actions dispatch through a workspace-aware store so undo,
  serialization, and cross-tab observers all just work.

### Document the contract

`TAB_CONTRACT.md` should describe:

- which hooks fire when,
- recommended way to use `state_slots` vs ad-hoc instance dicts,
- ownership rules for `resources` namespaces.

Right now contributors have no source of truth besides reading code.
