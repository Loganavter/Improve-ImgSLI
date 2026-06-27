# Multi Compare TODO

Tab-local backlog. Cross-cutting renderer/session work is mirrored in the
global [docs/dev/TODO.md](../../../../docs/dev/TODO.md).

## P1 - Move session snapshots into workspace `state_slots`

Status: `Open`

Current state:

- `MultiCompareTab` stores `dict[session_id -> MultiCompareState]` on the tab
  instance.
- `on_activated` snapshots/restores from that dict.
- `on_session_created` and `on_session_closed` are implemented locally, but the
  host does not yet invoke those hooks from workspace create/close.

Target:

- Store the active scene as `state_slots["multi_compare.scene"]`.
- Snapshot on activation/deactivation without a private tab-level dictionary.
- Clean up state automatically when the owning workspace session is closed.
- Keep `MultiCompareWidget` visual and bind it to the state selected by the
  active workspace session.

## P1 - Keep live/export rendering in one semantic path

Status: `Open`

Any future feature must be checked against both live canvas and GPU export:

- labels,
- dividers,
- drag/drop overlays,
- focused mode,
- transparent/background fill,
- resolution/aspect-ratio export settings.

Do not add a separate export-only layout path unless it preserves the same
canvas-px composition contract.

## P2 - Diff and analysis overlays

Status: `Design needed`

Multi Compare has no diff/analysis overlays yet. A future implementation must
decide whether comparison is pairwise, reference-slot based, or group-wide, and
must not leak main image-compare feature state into this tab.

## P2 - Magnifier integration

Status: `Design needed`

The main magnifier system is tied to the image-compare canvas. Multi Compare
needs either a tab-owned magnifier source or a host capability that can consume
the tab's composition/readback contract.

## P2 - Playlist/project persistence

Status: `Design needed`

Needed pieces:

- serialize slots and layout tree,
- define how image references are stored,
- restore label settings and split weights,
- decide whether export presets belong to the project or global settings.

## P2 - Tiled large-image support

Status: `Blocked`

Blocked on the global tiled rendering design. See
[docs/dev/TODO.md](../../../../docs/dev/TODO.md#p1---large-images-above-16384-px).
