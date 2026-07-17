# Tab System Documentation

How workspace tabs are structured, discovered, and wired to the host shell.
Each tab is a self-contained mini-module with its own resources, translations,
and state — the host provides a slot, session lifecycle, and platform services.

## Contents

- **[overview.md](overview.md)** — registered tabs, event routing, how to add a new tab
- **[package-structure.md](package-structure.md)** — file layout, i18n, tab-owned icons / help
- **[contract.md](contract.md)** — `TabContract` ABC, `TabContext`, design constraints
- **[registry.md](registry.md)** — `TabRegistry` discovery tiers, singleton, registry API
- **[session-lifecycle.md](session-lifecycle.md)** — workspace events, `state_slots`, project I/O
- **[capability-mechanisms.md](capability-mechanisms.md)** — host↔tab wiring: `create_service`, `notify_all`, `CanvasGeometryProvider`, policy & gaps
- **[isolation.md](isolation.md)** — resource isolation, no implied lookups, test ownership

**Core idea**: tabs never import host i18n, theme tokens, or `AppIcon`; new
host↔tab needs go through the fixed capability mechanisms — not new methods on
`TabContract`. See [capability-mechanisms.md](capability-mechanisms.md).
