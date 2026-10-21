# Tab System Documentation

How workspace tabs are structured, discovered, and wired to the host shell.
Each tab is a self-contained mini-module with its own resources, translations,
and state — the host provides a slot, session lifecycle, and platform services.

## Contents

- **[overview.md](overview.md)** — registered tabs, event routing, how to add a new tab
- **[package-structure.md](package-structure.md)** — file layout, i18n, tab-owned icons / help
- **[contract.md](contract.md)** — `TabContract` ABC / `TabContext` (interface contract; see [CONTRACTS.md](../CONTRACTS.md#three-senses-of-contract))
- **[registry.md](registry.md)** — `TabRegistry` discovery tiers, singleton, registry API
- **[session-lifecycle.md](session-lifecycle.md)** — workspace events, `state_slots`, project I/O
- **[capability-mechanisms.md](capability-mechanisms.md)** — host↔tab wiring: `create_service`, `notify_all`, `CanvasGeometryProvider`, policy & gaps
- **[background-tab-policy.md](background-tab-policy.md)** — what a hidden tab does today (verified), and what is deliberately not deferred
- **[isolation.md](isolation.md)** — resource isolation, no implied lookups, test ownership

**Core idea**: tabs never import host i18n, theme tokens, or `AppIcon`; a new
host↔tab need goes through the fixed capability mechanisms (or an existing named
hook family on `TabContract`) rather than a new ad-hoc callback. See
[capability-mechanisms.md](capability-mechanisms.md) and
[contract.md](contract.md).

**Tab-owned docs** (architecture notes, investigations) live under
`src/tabs/<tab>/docs/`, not here — see
[image_compare/docs/](../../../src/tabs/image_compare/docs/),
[multi_compare/docs/](../../../src/tabs/multi_compare/docs/),
[image_gallery/docs/](../../../src/tabs/image_gallery/docs/) and
[session_picker/docs/](../../../src/tabs/session_picker/docs/). This page and
the rest of `docs/dev/` cover only the host↔tab contract shared by every tab.
