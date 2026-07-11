# Development Documentation

In-depth guides about architecture, contracts, and component design for contributors.

## Quick Links

- **[CONTRACTS.md](CONTRACTS.md)** — Complete reference of all 24+ contracts and protocols used in the application
- **[ARCHITECTURE.md](ARCHITECTURE.md)** — Overall architectural design and patterns
- **[QRHI_CANVAS_FEATURES.md](QRHI_CANVAS_FEATURES.md)** — Canvas feature system, how to add new features, and zoom/pan invariants
- **[RHI_RENDERER_REFACTOR.md](RHI_RENDERER_REFACTOR.md)** — plan: split `rhi_renderer.py`'s six mixed concerns into owned modules (residency, geometry, uniforms, GPU resource lifecycle, draw orchestration)
- **[CANVAS_FEATURE_REGISTRY_PER_TAB.md](CANVAS_FEATURE_REGISTRY_PER_TAB.md)** — plan: split the shared canvas feature registry into per-tab instances
- **[TRACING.md](TRACING.md)** — Runtime tracer for debugging Redux/EventBus/render causal chains
- **[UI_INSPECTOR.md](UI_INSPECTOR.md)** — Developer UI inspector for widget colors, QSS candidates, and theme tokens
- **[TESTING.md](TESTING.md)** — Test suite layout (`/tests`), per-file catalog, how to run, and conventions for new tests
- **[TAB_CONTRACT.md](TAB_CONTRACT.md)** — Workspace tab interface and tab system design
- **[UI_TOOLKIT_LIBRARY.md](UI_TOOLKIT_LIBRARY.md)** — Custom UI toolkit (sli-ui-toolkit) API and components
- **[HELP_WIDGET.md](HELP_WIDGET.md)** — Help system widget implementation
- **[CPP_PORT_HARDENING.md](CPP_PORT_HARDENING.md)** — Plan for bringing the C++/Rust port up to product parity with the Python build (visual design, structural cleanup, remaining feature pipelines)

## For Users

See **[INSTALL.md](../INSTALL.md)** in the parent directory for installation instructions.

## For Developers

Start with [ARCHITECTURE.md](ARCHITECTURE.md) for an overview of design patterns and layers. Then:

1. To add a new canvas feature → read [QRHI_CANVAS_FEATURES.md](QRHI_CANVAS_FEATURES.md)
2. To understand component protocols → see [CONTRACTS.md](CONTRACTS.md)
3. To add a new workspace tab → read [TAB_CONTRACT.md](TAB_CONTRACT.md)
4. To create custom UI widgets → check [UI_TOOLKIT_LIBRARY.md](UI_TOOLKIT_LIBRARY.md)
5. To debug "something weird happened after I clicked / zoomed" → read [TRACING.md](TRACING.md)

## Architecture Summary

The application uses:
- **Redux pattern** for state management (actions → reducers → store)
- **Plugin system** for modular features with **feature isolation** (each feature operates in a simplified abstraction layer — no direct coordinate transforms, events, or serialization)
- **Contract-based architecture** with 24+ defined interfaces (no direct feature imports in shared code)
- **Feature auto-discovery** via registry pattern (add a feature by copying a template; no central registration needed)
- **Canvas feature system** for visual editor tools (magnifier, divider, guides, etc.)
- **Custom PySide6/OpenGL rendering pipeline**

See [ARCHITECTURE.md](ARCHITECTURE.md) and [Feature Isolation Model](./CONTRACTS.md#feature-isolation-model-the-abstraction) for complete details.
