# Comparison plugin

`ComparisonPlugin` (`src/tabs/image_compare/plugin.py`) is the tab-owned
plugin for the Image Compare workspace — the primary two-image comparison
tab. It registers the `image_compare` session type, owns the analysis
services, the session controller, and the canvas.

Tab architecture: [ARCHITECTURE.md](../ARCHITECTURE.md). Plugin system:
[docs/dev/PLUGINS.md(../../../../../docs/dev/PLUGINS.md). This plugin is the
canonical "reference plugin" used as the template for new plugins (see
[PLUGINS.md(../../../../../docs/dev/PLUGINS.md#reference-plugin-comparison)).

## Wiring

`@plugin(name="comparison", startup_tier="bootstrap")`. Implements
`ISessionPlugin`.

- `initialize(context)` stores `store`, `event_bus`, `thread_pool`; constructs
  `SessionController` and other tab services (never in `__init__`).
- `get_session_blueprints()` returns the `image_compare` session blueprint.

## Notes

- There is **no** `@plugin(name="analysis")`. Diff/metrics/SSIM live under
  `tabs/image_compare/services/analysis/` and `shared/analysis/`, constructed
  by `ComparisonPlugin`.
- `comparison` is both the plugin and the `image_compare` tab — its plugin
  lives under `src/tabs/image_compare/` instead of `src/plugins/`, but
  discovery scans both trees, so it's a normal plugin to the host.
