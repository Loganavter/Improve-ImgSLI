# Workspace session lifecycle

Events (see [EVENT_BUS.md](../EVENT_BUS.md)) are emitted from
`WorkspaceSessionActions` (`core/main_controller_parts/sessions.py`) and routed
in `ui/main_window/layouts.py`:

| Event | When | Tab hook |
|---|---|---|
| `WorkspaceSessionCreatedEvent` | After `create_workspace_session` | `on_session_created` |
| `WorkspaceSessionClosedEvent` | After `close_workspace_session` | `on_session_closed` |
| `WorkspaceSessionActivatedEvent` | After create (if activate), switch, or close promoted a new active session | `on_active_session_changed` (when tab type matches) |

`TabRegistry.activate(session_type)` still fires `on_activated` when the
**tab type** changes. Same-type session switches (IC→IC) go through
`on_active_session_changed` only.

The bootstrap `session_picker` created inside `Store.__init__` does **not**
emit `WorkspaceSessionCreatedEvent` — intentional; `SessionPickerTab` has no
create hook work to do.

## `state_slots`

Per-session arbitrary state lives on `WorkspaceSession.state_slots` (see
`core/store_workspace.py`). Prefer blueprint factories in `SessionBlueprint` for
defaults; use `store.ensure_session_state_slot` / `set_session_state_slot` with
an explicit `session_id=` when snapshotting from tab hooks.

`state_slots["action_history"]` holds the per-session undo list (append-only
skeleton today — no undo/redo UI yet). `Dispatcher.bind_history_for_session`
swaps the active list on `WorkspaceSessionActivatedEvent`.

## Project I/O

`services/io/project_io.py` writes portable **ZIP** `.imgsli` packages
(version 2): `project.json` plus byte-copied originals under
`media/<asset_id>/`. Paths inside session blobs are rewritten to package
members on save and to a per-project extract cache on load. Legacy plain-JSON
v1 files remain loadable (path references only).

`serialize_session` / `deserialize_session` / `rehydrate_session` go through
`TabRegistry`. Use `load_project_file(..., replace_workspace=True)` (the Open
Project default) for a clean workspace replace. Tabs that return `None` from
`serialize_session` (e.g. `session_picker`) are omitted from saves.

Image Compare session blobs include viewport/view settings, canvas feature
property settings, magnifier instances, and camera (zoom/pan). Multi Compare
keeps layout/zoom/pan/labels/dividers. Pixel buffers are never embedded —
only file copies.

Duplicate: `WorkspaceSessionActions.duplicate_workspace_session` →
`duplicate_session` snapshot → new session → `deserialize_session` →
`rehydrate_session`.

For code that must run loaders against a non-active session (project
rehydrate), use `store.using_workspace_session(session_id)` — a public
context manager on `WorkspaceStoreMixin` that temporarily swaps the active
session and restores the previous one on exit.

Multi Compare: every new `multi_compare` session seeds divider/label chrome
from QSettings last-used prefs (`_settings_from_qsettings`), falling back to
another live MC session's slot when QSettings is empty. Live slots stay
isolated after seed — editing one tab does not mutate another's slot.
