# Session Picker plugin

`SessionPickerPlugin` (`src/tabs/session_picker/plugin.py`) is the tab-owned
plugin for the Session Picker workspace. It registers the transient
`session_picker` session type.

Tab layout: [README.md](../README.md). Plugin system:
[docs/dev/PLUGINS.md(../../../../../docs/dev/PLUGINS.md).

## Wiring

`@plugin(name="session_picker", startup_tier="bootstrap")`. Implements
`ISessionPlugin`.

- `initialize(context)` stores `store`.
- `get_session_blueprints()` returns a `SessionBlueprint` for
  `session_picker` titled "New Tab" with `metadata_defaults={"transient":
  True}` — a transient session that lives on the startup stack without
  persisting as a real workspace.

## Notes

- Session types are looked up by `PluginCoordinator.create_session` from this
  plugin — not from `TabRegistry` (which only wires the page/UI). Both must
  exist for a tab to be creatable from the New Session picker.
