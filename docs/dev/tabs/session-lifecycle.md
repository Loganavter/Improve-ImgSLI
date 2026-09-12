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

`state_slots["action_history"]` holds the per-session dispatched-action log.
`state_slots["undo_stack"]` / `["redo_stack"]` hold reference-snapshots for
**undo/redo** (`Dispatcher.undo()/redo()`, Ctrl+Z / Ctrl+Shift+Z / Ctrl+Y,
palette entries `platform.undo`/`platform.redo`, and CSD title-bar buttons in
the leading zone after the menu strip — `MenuController._install_undo_redo_buttons`,
styled like File/Help triggers, disabled at 0.4 opacity, enabled-state
refreshed from `can_undo()/can_redo()` on store change).
`Dispatcher.bind_history_for_session`
swaps all three on `WorkspaceSessionActivatedEvent`.

Undo records only "user-meaningful" actions (`Dispatcher._UNDOABLE_TYPES`):
viewport/appearance/feature settings and `SET_CURRENT_INDEX` for image
compare, plus the multi_compare session actions. Global settings, transient
interaction/visual state, caches/metrics, and pixel-bearing document actions
(which close the replaced `TiledPixelStore`) are excluded. Continuous
gestures coalesce to one undo step (`_COALESCE_TYPES`). Undo is blocked while
`render_cache.unification_in_progress` is set (image loading). Redo clears on
the next dispatch. Both image_compare and multi_compare flow through the same
core `Dispatcher`, so undo/redo (and the CSD buttons) cover both.

## Project I/O

`services/io/project_io.py` writes portable **ZIP** `.imgsli` packages
(version 2): `project.json` plus byte-copied originals under
`media/<asset_id>/`, and optional top-level `preview.png` (cover-scaled grab
of the active workspace canvas). Paths inside
session blobs are rewritten to package members on save and to a per-project
extract cache on load. Legacy plain-JSON v1 files remain loadable (path
references only).

**Linux desktop integration** (MIME + open-with + FM thumbnails):

- MIME: `application/x-improve-imgsli` (`build/linux/mime/…`) with:
  - magic priority 80: `PK\003\004` + first ZIP local name `project.json`
    (beats `application/zip` magic at 60 — glob alone is not enough for
    GIO/Dolphin, which prefer content sniffing)
  - high-weight `*.imgsli` globs as a fallback for empty/corrupt packages
  - document-style MIME icons (`build/linux/icons/mimetypes/…`: page + mark +
    `IMGSLI`, PSD/XCF layout — not a full-bleed wordmark)
- Desktop `MimeType=` + `Exec=… %F` opens a project path on startup
- Thumbnailer composites `preview.png` into a document frame with a small
  app-mark badge (`build/linux/bin/improve-imgsli-thumbnailer`)
- After install, KDE needs `kbuildsycoca6` (done by `install-desktop`); restart Dolphin if the type still shows as Zip

Install from source: `./launcher.sh run` (auto-syncs MIME/desktop on Linux) or
`./launcher.sh install-desktop`. Packaged via AUR/Flatpak
templates under `build/`.

**Windows file association** (ProgID + icon + Open):

1. **Installer (Inno):** task `fileassoc` writes HKLM
   `Software\Classes\.imgsli` → `ImproveImgSLI.Project` with
   `DefaultIcon` (`icons\imgsli-file.ico`) and
   `shell\open\command` → `Improve_ImgSLI.exe "%1"`.
2. **Frozen app startup:** also idempotently registers the same ProgID under
   HKCU (`services/system/windows_file_association.py`) so portable/unzipped
   builds get Open-with without reinstall. Force with
   `Improve_ImgSLI.exe --register-file-types`.
3. **Content thumbnails (optional later):** COM `IThumbnailProvider` reading
   `preview.png` — separate native shell extension; Explorer will keep using
   the ProgID icon until that exists. Microsoft docs:
   [Thumbnail Handlers](https://learn.microsoft.com/en-us/windows/win32/shell/thumbnail-providers).
4. If Properties still shows “Choose application”, pick Improve ImgSLI once
   (or re-run the installer with file association checked / `--register-file-types`).
   A prior “Open with → Explorer/ZIP” UserChoice may need resetting in
   Settings → Default apps.

**macOS:** later — UTI + Quick Look generator; same canvas ``preview.png`` can feed QL.

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

Multi Compare's session state is `state_slots["multi_compare.state"]`,
reduced by the core `RootReducer` (registered in
`tabs/multi_compare/bootstrap_reducers.py`) and written back by the core
Dispatcher, so **undo/redo, serialization, and observers all go through the
same path** as image_compare. `MultiCompareStore` is a facade over the core
Dispatcher + active session slot (see
`src/tabs/multi_compare/docs/ARCHITECTURE.md` / `state-unification-plan.md`).
MC action types are in `Dispatcher._UNDOABLE_TYPES`, so Ctrl+Z /
Ctrl+Shift+Z / Ctrl+Y and the CSD undo/redo buttons work in Multi Compare
too. `RemoveSlot`/`Clear` defer closing removed `TiledPixelStore`s so an undo
of a removal restores a still-open store.