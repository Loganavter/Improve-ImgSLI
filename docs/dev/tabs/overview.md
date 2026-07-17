# Overview

The tab system allows adding new operation modes to the application without
modifying the core codebase.

## Registered tabs

| Package | Role |
|---|---|
| `tabs/image_compare/` | Primary two-image comparison — full canvas, overlays, guides, capture circles, split view, video editor integration |
| `tabs/multi_compare/` | Grid-layout multi-image comparison, composition-aware rendering |
| `tabs/session_picker/` | Workspace session browser / new-session switcher |

## Event routing

- **Page switching**: `sync_session_mode(session_type)` checks the registry. If the type is found, it displays the tab's page and calls `activate()`.
- **Drag & drop**: `WindowEventHandler` checks the active session. If its type is registered in the registry, it calls `registry.route_drop()`.
- **Visibility settings**: Controlled via a checkbox in Settings > Appearance. The tab bar is hidden by default.

## How to add a new tab

1. Create a package in `src/tabs/<name>/`.
2. Implement the `TabContract` in `tab.py` (see [contract.md](contract.md)).
3. Create the widget and controller.
4. Add translation files to `resources/i18n/` (see [package-structure.md](package-structure.md)).
5. Add `icons.py` + `resources/icons/{light,dark}/` if the tab has toolbar or other custom icons.
6. Add tests under `src/tabs/<name>/tests/` (see [isolation.md](isolation.md)).
7. Done — the registry picks it up automatically.

No changes are required in `main_window_ui.py`, `window_event_handler.py`, or other core files.
