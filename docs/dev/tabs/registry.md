# TabRegistry

The registry discovers tabs in **bootstrap** and **deferred** tiers (see
`src/core/plugin_system/discovery_scan.py` for module lists):

| Tier | Tab modules | When |
|---|---|---|
| `bootstrap` | tabs with `startup_tier = "bootstrap"` on `TabContract` | `ui/main_window/layouts.py` during `setupUi` |
| `deferred` | tabs with `startup_tier = "deferred"` (default) | After `startupVisualReady` |

Tier is read from each tab class's `startup_tier` class attribute (AST scan of
`tab.py` before import). Override on the tab class; default is `"deferred"`.

1. Imports `tabs.<name>.tab` for each package in the tier.
2. Locates subclasses of `TabContract`.
3. Creates instances and registers them by `session_type` (skips types already registered).

Packages with a `_` prefix are ignored. The `contract` and `registry` modules are skipped.

`TabRegistry` is a **process-wide singleton** (`tabs/registry.py`, `__new__`)
— strict active-tab routing (see [capability-mechanisms.md](capability-mechanisms.md))
only makes sense if `_active_session_type` is a single, consistent value
everywhere. `discover()` with no `tier` ensures bootstrap then deferred
(idempotent per tier). `discover(tier="bootstrap")` alone is used during initial
shell construction; `get_shared_tab_registry()` also loads bootstrap tabs only
on first access.

Use `install_missing_pages(stack)` after deferred discovery to add workspace
pages for tabs registered after the initial `install_pages()` call.

## Registry API

```python
registry = TabRegistry()
registry.discover(tier="bootstrap")                     # Bootstrap tabs only
registry.discover(tier="deferred")                    # Add multi_compare
registry.discover()                                   # Ensure all tiers (defensive)
registry.install_pages(stack, context)                # Create pages in QStackedWidget
registry.install_missing_pages(stack)                 # Deferred tabs after first install
registry.get_page(session_type) -> QWidget             # Retrieve page by type
registry.activate(session_type)                        # Notify activation
registry.activate_default()                             # Activate the is_bootstrap_default tab
registry.deactivate(session_type)                       # Notify deactivation
registry.route_drop(session_type, paths)                # Route drag-and-drop
registry.create_service(service_id, *args, **kwargs)    # Active-tab-only dispatch
registry.create_startup_service(service_id, *a, **kw)   # Bootstrap-default-tab-only dispatch
registry.create_main_window_feature(feature_id, **kw)   # Active-tab-only; do not extend (single-ID hook)
registry.notify_all(hook_id, *args, **kwargs)           # Broadcast to every registered tab
registry.dispose_all()                                  # Cleanup
registry.notify_session_created(session_type, session_id)
registry.notify_session_closed(session_type, session_id)
registry.notify_active_session_changed(session_id, session_type, previous_id)
registry.serialize_session(session_type, session_id)
registry.deserialize_session(session_type, session_id, data)
registry.rehydrate_session(session_type, session_id)
registry.duplicate_session(session_type, source_session_id)
```

Implementation: `src/tabs/registry.py`.
