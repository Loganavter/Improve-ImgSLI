# Image Gallery plugin

`ImageGalleryPlugin` (`src/tabs/image_gallery/plugin.py`) is the tab-owned
plugin for the Image Gallery workspace. It registers the `image_gallery`
session type.

Tab layout: [README.md](../README.md). Plugin system:
[docs/dev/PLUGINS.md](../../../../../docs/dev/PLUGINS.md).

## Wiring

`@plugin(name="image_gallery", startup_tier="deferred")`. Implements
`ISessionPlugin`.

- `initialize(context)` stores `store` + `event_bus`.
- `get_session_blueprints()` returns a `SessionBlueprint` for
  `image_gallery` titled "Image Gallery", with a fresh state slot
  (`{"folder": None}`).

## Notes

- This is the older, separate plugin/session-blueprint registration path.
  `PluginCoordinator.create_session` looks up session types here, not in
  `TabRegistry` (which only wires the tab's page/UI). Both must exist for a
  tab to be creatable from the New Session picker — see
  `src/tabs/multi_compare/plugin.py` for the template this mirrors.
