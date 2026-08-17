# Multi Compare plugin

`MultiComparePlugin` (`src/tabs/multi_compare/plugin.py`) is the tab-owned
plugin for the Multi Compare workspace. It registers the `multi_compare`
session type and its state slot.

Tab architecture: [README.md](../README.md),
[ARCHITECTURE.md](../ARCHITECTURE.md). Plugin system:
[docs/dev/PLUGINS.md(../../../../../docs/dev/PLUGINS.md).

## Wiring

`@plugin(name="multi_compare", startup_tier="deferred")`. Implements
`ISessionPlugin`.

- `initialize(context)` stores `store` + `event_bus` and calls
  `register_multi_compare_reducers()` (from `bootstrap_reducers.py`).
- `get_session_blueprints()` returns a `SessionBlueprint` for
  `multi_compare` with a `multi_compare.state` slot whose factory is
  `tabs.multi_compare.tab._fresh_default_state`.

## Notes

- Session types are looked up by `PluginCoordinator.create_session` from this
  plugin — not from `TabRegistry` (which only wires the page/UI). This file is
  the template newer session plugins mirror.
