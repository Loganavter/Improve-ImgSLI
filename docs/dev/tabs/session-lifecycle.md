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

`services/io/project_io.py` calls `serialize_session` / `deserialize_session` /
`rehydrate_session` via `TabRegistry`. Use `load_project_data(...,
replace_workspace=True)` for a clean programmatic open. Tabs that return
`None` from `serialize_session` (e.g. `session_picker`) are omitted from saves.

Duplicate: `WorkspaceSessionActions.duplicate_workspace_session` →
`duplicate_session` snapshot → new session → `deserialize_session` →
`rehydrate_session`.

For code that must run loaders against a non-active session (project
rehydrate), use `store.using_workspace_session(session_id)` — a public
context manager on `WorkspaceStoreMixin` that temporarily swaps the active
session and restores the previous one on exit.

Multi Compare: the first `multi_compare` session in a workspace may seed
divider/label defaults from QSettings (`_settings_from_qsettings`); every
subsequent MC session in that workspace gets blueprint fresh defaults.
