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

**Windows (not implemented yet — recommended path):**

1. **Minimum (file type + icon):** register a ProgID for `.imgsli` with
   `DefaultIcon` pointing at an `.ico` (or DLL resource) of the app mark.
   Installer (Inno/MSIX/WiX) writes `HKCU\Software\Classes` (or HKLM) and
   sets “Open with” → `Improve-ImgSLI.exe "%1"`. Explorer will then stop
   treating the file as a generic ZIP *if* the ProgID wins over ZIP sniffing
   (same story as `.docx` / `.cbz`: distinctive extension + registered type).
2. **Content thumbnails (optional later):** implement an in-process COM
   `IThumbnailProvider` (+ `IInitializeWithStream`) DLL that opens the ZIP
   stream, reads `preview.png` (or legacy `preview.jpg`), and returns an `HBITMAP`. Register under
   `.<ext>\ShellEx\{E357FCCD-A995-4576-B01F-234630154E96}`. Microsoft docs:
   [Thumbnail Handlers](https://learn.microsoft.com/en-us/windows/win32/shell/thumbnail-providers).
   This is a separate native (or Rust) shell extension — not something PySide
   can host cleanly inside the main EXE.
3. Until (1)/(2) exist, double-click / branded thumbs on Windows are best-effort;
   the in-app Session Picker already shows `preview.png` (canvas grab) or the
   session-type icon when missing.

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
