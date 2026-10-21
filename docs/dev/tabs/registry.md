# TabRegistry

The registry discovers tabs in three tiers (`TabDiscoveryTier` in
`src/tabs/registry.py`; module lists come from
`src/core/plugin_system/discovery_scan.py`):

| Tier | Tab modules | When |
|---|---|---|
| `bootstrap` | tabs with `startup_tier = "bootstrap"` on `TabContract` | `ui/main_window/layouts.py` during `setupUi` |
| `deferred` | tabs with `startup_tier = "deferred"` (default) | After `startupVisualReady` |
| `all` | every package under `src/tabs/` with a `tab.py` (pkgutil scan, no AST tier filter) | Test/contract tooling (`tests/contracts/test_tabs_isolation.py`); not a startup path |

Tier is read from each tab class's `startup_tier` class attribute (AST scan of
`tab.py` before import). Override on the tab class; default is `"deferred"`, and
an invalid value fails at import time. Within a tier, registration order is
sorted package name (`discovery_scan.py` sorts `tabs/` entries); with no `tier`
argument the registry runs bootstrap first, then deferred.

1. Imports `tabs.<name>.tab` for each package in the tier.
2. Locates subclasses of `TabContract`.
3. Creates instances and registers them by `session_type` (skips types already registered).
4. Registers each instance's canvas features, extra i18n roots and
   `create_default_session_data` factory (`tabs/use_cases/discovery.py`).

Packages with a `_` prefix are ignored. The `contract` and `registry` modules are
skipped. `tab_packages_for_tier` also finds a tab's own `plugin.py` and nested
`plugins/*/plugin.py` (see [overview.md](overview.md) — the picker needs the
plugin, not just the tab).

`TabRegistry` is a **process-wide singleton** (`tabs/registry.py`, `__new__`)
— strict active-tab routing (see [capability-mechanisms.md](capability-mechanisms.md))
only makes sense if `_active_session_type` is a single, consistent value
everywhere. `discover()` with no `tier` ensures bootstrap then deferred
(idempotent per tier). `discover(tier="bootstrap")` alone is used during initial
shell construction; `get_shared_tab_registry()` also loads bootstrap tabs only
on first access and is the entry point for hot-path lookups (per-frame /
per-mouse-move code must not re-run discovery).

Pages are **lazy**. `install_pages(stack, context)` stores the context/stack and
records every registered tab as a *pending* page; `activate()` builds the page on
first show (`tabs/use_cases/pages.py`). Use `install_missing_pages(stack)` after
deferred discovery to record tabs registered after the initial `install_pages()`
call — it also creates nothing.

## If a tab fails to load

Discovery is contained per module: an import error, a constructor error or an
invalid `startup_tier` in one tab is logged with `logger.exception` and only that
tab is skipped — the rest of the tier still registers
(`tabs/use_cases/discovery.py`). Two tabs claiming one `session_type` keep the
first and log the collision at error level. Consequence for whoever is
debugging a missing tab: it **disappears from the UI silently** and the reason is
in the log (`~/.local/share/Improve-ImgSLI/log.txt`), not in the widget tree.

## Registry API

```python
registry = TabRegistry()                                # process-wide singleton
registry.discover(tier="bootstrap")                     # Bootstrap tabs only
registry.discover(tier="deferred")                      # Add deferred tabs
registry.discover()                                     # Ensure all tiers (defensive)
registry.discover(tier="all")                           # pkgutil scan (tests)

registry.registered_types -> list[str]                  # session types, registration order
registry.deferred_loaded -> bool                        # has the deferred tier been imported
registry.get_tab(session_type) -> TabContract | None
registry.get_active_tab() -> TabContract | None         # None before the first activation
registry.list_tabs() -> list[TabContract]

registry.install_pages(stack, context)                  # Record pending pages (creates nothing)
registry.install_missing_pages(stack)                   # Record tabs from a later tier
registry.get_page(session_type) -> QWidget | None        # Only after first activation
registry.activate(session_type)                          # Build-if-needed + activate
registry.activate_default()                              # Activate the is_bootstrap_default tab (session_picker only)
registry.deactivate(session_type)                        # Notify deactivation
registry.route_drop(session_type, paths)                 # Route drag-and-drop

registry.create_service(service_id, *args, **kwargs)     # Active-tab-only dispatch
registry.create_service_for(session_type, service_id, …)  # Named hub tab (e.g. session picker)
registry.create_startup_service(service_id, *a, **kw)    # By capability: first tab that answers
registry.create_main_window_feature(feature_id, **kw)    # By capability: first tab that answers (do not extend)
registry.notify_all(hook_id, *args, **kwargs)            # Broadcast to every registered tab

registry.contribute_all_settings()                       # Typed settings contributions
registry.contribute_all_help()                           # Typed help contributions
registry.contribute_settings_for(session_type)           # One tab's contributions (after lazy page build)

registry.assemble_host_pages(ui)                         # Legacy host-page seam (created pages only)
registry.finalize_host_pages(ui)                         # Cosmetic pass (active tab's page)
registry.apply_host_session_mode(session_type, ui, session_title=…) -> bool
registry.apply_appearance(host_window)                    # Theme flip, hidden pages deferred
registry.flush_stale_appearance(host_window)             # Flush a deferred theme flip on show
registry.notify_window_shutdown(host_window)             # Tab teardown hook

registry.notify_session_created(session_type, session_id)
registry.notify_session_closed(session_type, session_id)
registry.notify_active_session_changed(session_id, session_type, previous_id)
registry.serialize_session(session_type, session_id)
registry.collect_pixel_cache_sources(session_type, session_id)
registry.deserialize_session(session_type, session_id, data)
registry.rehydrate_session(session_type, session_id)
registry.duplicate_session(session_type, source_session_id)
registry.dispose_all()                                   # Cleanup (drops every page)
```

Module-level: `get_shared_tab_registry() -> TabRegistry` (bootstrap-only shared
instance) and `LazyTabService` (re-exported from `tabs/lazy_tab_service.py`).

Implementation: `src/tabs/registry.py`.
