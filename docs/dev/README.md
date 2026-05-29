# Development Documentation

In-depth guides about architecture, contracts, and component design for contributors.

## Quick Links

- **[CONTRACTS.md](CONTRACTS.md)** — Complete reference of all 24+ contracts and protocols used in the application
- **[ARCHITECTURE.md](ARCHITECTURE.md)** — Overall architectural design and patterns
- **[CANVAS_FEATURES.md](CANVAS_FEATURES.md)** — Canvas feature system, how to add new features, and zoom/pan invariants
- **[TRACING.md](TRACING.md)** — Runtime tracer for debugging Redux/EventBus/render causal chains
- **[TESTING.md](TESTING.md)** — Test suite layout (`/tests`), per-file catalog, how to run, and conventions for new tests
- **[TAB_CONTRACT.md](TAB_CONTRACT.md)** — Workspace tab interface and tab system design
- **[UI_TOOLKIT_LIBRARY.md](UI_TOOLKIT_LIBRARY.md)** — Custom UI toolkit (sli-ui-toolkit) API and components
- **[HELP_WIDGET.md](HELP_WIDGET.md)** — Help system widget implementation

## For Users

See **[INSTALL.md](../INSTALL.md)** in the parent directory for installation instructions.

## For Developers

Start with [ARCHITECTURE.md](ARCHITECTURE.md) for an overview of design patterns and layers. Then:

1. To add a new canvas feature → read [CANVAS_FEATURES.md](CANVAS_FEATURES.md)
2. To understand component protocols → see [CONTRACTS.md](CONTRACTS.md)
3. To add a new workspace tab → read [TAB_CONTRACT.md](TAB_CONTRACT.md)
4. To create custom UI widgets → check [UI_TOOLKIT_LIBRARY.md](UI_TOOLKIT_LIBRARY.md)
5. To debug "something weird happened after I clicked / zoomed" → read [TRACING.md](TRACING.md)

## Architecture Summary

The application uses:
- **Redux pattern** for state management (actions → reducers → store)
- **Plugin system** for modular features
- **Contract-based architecture** with 24+ defined interfaces
- **Feature auto-discovery** via registry pattern
- **Canvas feature system** for visual editor tools (magnifier, divider, guides, etc.)
- **Custom PyQt6/OpenGL rendering pipeline**

See [ARCHITECTURE.md](ARCHITECTURE.md) for complete details.
