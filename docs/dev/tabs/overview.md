# Overview

The tab system allows adding new operation modes to the application without
modifying the core codebase.

## Registered tabs

| Package | Role |
|---|---|
| `tabs/image_compare/` | Primary two-image comparison — full canvas, overlays, guides, capture circles, split view, video editor plugin |
| `tabs/multi_compare/` | Grid-layout multi-image comparison, composition-aware rendering |
| `tabs/image_gallery/` | Folder-level triage gallery — own `analysis/` engine wiring, `state/` slice, AI judge/profile layer, quick look |
| `tabs/session_picker/` | Workspace session browser / new-session switcher |

Each package is two registrations, not one: `tab.py` (the `TabContract`
implementation, wired by `TabRegistry`) and `plugin.py` (`@plugin(...)` +
`ISessionPlugin`, where `PluginCoordinator.create_session` looks the session type
up). `image_compare`'s plugin is named `comparison`; the other three use their
package name.

## Event routing

- **Page switching**: `sync_session_mode(session_type)` checks the registry. If the type is found, it displays the tab's page and calls `activate()`.
- **Drag & drop**: `WindowEventHandler` checks the active session. If its type is registered in the registry, it calls `registry.route_drop()`.
- **Tab strip**: always present — `WorkspaceTabStrip` is built in
  `ui/main_window/ui.py` `_create_static_widgets` and synced from the session
  list (`ui/presenters/main_window/workspace.py`). There is no visibility
  setting for it.

## How to add a new tab

1. Create a package in `src/tabs/<name>/`.
2. Implement the `TabContract` in `tab.py` (see [contract.md](contract.md)) —
   `session_type`, `display_name`, `create_page` are the required minimum.
3. Create the widget and controller.
4. Add `plugin.py` with `@plugin(name="<name>", startup_tier=...)` and an
   `ISessionPlugin` implementation returning `get_session_blueprints()` (copy
   `tabs/multi_compare/plugin.py`; register the tab's reducers from
   `initialize`). Without this step the tab is discovered and its page can be
   built, but it is **not creatable** from the New Session picker.
5. Answer `create_service("topology_overlays", parent)` (return `[]` if the tab
   owns no window-parented modals) — a runtime test enforces this for every
   registered tab.
6. Add translation files to `resources/i18n/` (see [package-structure.md](package-structure.md)).
7. Add `icons.py` + `resources/icons/{light,dark}/` if the tab has toolbar or other custom icons.
8. Add tests under `src/tabs/<name>/tests/` (see [isolation.md](isolation.md)).
9. Done — discovery picks both `tab.py` and `plugin.py` up automatically.

No per-tab changes are required in `ui/main_window/layouts.py`,
`ui/main_window/ui.py` or `src/events/window_event_handler.py`: the host routes
by registry lookup.
