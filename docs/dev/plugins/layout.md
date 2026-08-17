# Layout plugin

UI-mode subscriber for the app-wide chrome: listens for `ui_mode` changes and
applies them to the tab-provided layout manager, plus re-syncs action
shortcuts.

Source: `src/plugins/layout/`. Plugin system: [PLUGINS.md](../PLUGINS.md).

## Wiring

`@plugin(name="layout", startup_tier="bootstrap")`. No contribution
interfaces — it only subscribes to `SettingsUIModeChangedEvent`.

- `initialize(context)` stores `store` + `event_bus`, subscribes
  `SettingsUIModeChangedEvent` → `_on_ui_mode_changed_event`.
- `setup_ui_reference(ui, parent_window=None)` — called by the host after the
  main window exists. It obtains the tab-provided
  `layout_manager` via `TabRegistry.create_startup_service("layout_manager",
  ui, parent_window)` (NOT a local manager module), then applies the current
  stored `ui_mode`.
- `on_ui_mode_changed(mode_name)` applies the mode through the manager and
  re-syncs action shortcuts via `ui.actions.binder.resync_action_shortcuts`.

## Notes

- The layout manager itself is owned by a tab (see
  [tabs/index.md](../tabs/index.md) `create_startup_service`); the plugin is
  only the mode-fanout subscriber.
- `toast_manager` is exposed for host convenience.
- UI modes: `beginner`, `advanced`, `expert`, `minimal` (validation lives in
  the settings plugin controller).
