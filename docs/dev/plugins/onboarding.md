# Onboarding plugin

First-run UI-mode picker: a full-window overlay that walks the user through
the available UI modes (beginner / advanced / expert) and applies the chosen
mode. It appears **over the first compare tab the user opens** — not on the
session picker, not on other tabs — and fires **once per install across all
onboarding-capable tabs**.

Source: `src/plugins/onboarding/`. Plugin system: [PLUGINS.md](../PLUGINS.md).

## Triggering (tab-scoped, one-shot)

Onboarding no longer shows at app startup. The plugin subscribes to
`WorkspaceSessionActivatedEvent` in `initialize`; when a session activates it
asks the opened tab whether it opts into first-run onboarding via the
`requires_first_run_onboarding` capability (see
[capability-mechanisms.md](../tabs/capability-mechanisms.md)):

```python
registry.create_service_for(session_type, "requires_first_run_onboarding")
```

- The query is **tab-agnostic** — the plugin never names `image_compare` /
  `multi_compare` (platform code must not; `tests/contracts/test_platform_isolation.py`).
- Tabs opt in by answering `True` for `requires_first_run_onboarding` in their
  `create_service` (currently `image_compare` and `multi_compare`).
- **One shot across all onboarding tabs**: `should_present()` gates on
  `SettingsManager.is_first_run()`, which flips off on completion — so opening
  a second onboarding-capable tab later never re-shows.
- The session picker and non-onboarding tabs (e.g. image_gallery) never trigger it.

## Wiring

`@plugin(name="onboarding", startup_tier="bootstrap")`. No contribution
interfaces.

- `initialize(context)` stores `store`, `settings_manager`, `event_bus` and
  subscribes `WorkspaceSessionActivatedEvent`.
- `_on_session_activated(event)` — if not already active, first-run is still
  pending, and the opened tab answers the onboarding capability → `present()`.
- `_tab_requests_onboarding(session_type)` — capability probe via
  `get_shared_tab_registry().create_service_for`.
- `bind_window_shell(window_shell)` resolves the main window, registers itself
  as `window.onboarding_host`, and caches `startup_runtime.on_onboarding_completed`
  as the default completion callback.
- `should_present()` → true when `SettingsManager.is_first_run()`.
- `present(window, on_completed=...)` mounts `OnboardingOverlay` on the
  window's `_startup_stack`, resizes to the stack/window, prepares for
  display, focuses it, and hides the startup cover.
- `dismiss()`, `sync_geometry()`, `prepare_after_show()` — lifecycle helpers
  used by the host.
- `apply_ui_mode(mode_key)` / `_apply_ui_mode` sets `store.settings.ui_mode`,
  emits `SettingsUIModeChangedEvent`, and re-applies toolbar styles.

## Key modules

| Module | Role |
|---|---|
| `overlay.py` | `OnboardingOverlay` — full-window slide overlay; emits `completed(mode_key)` |
| `pages.py` | `build_modes`, `create_slide_for_mode`, per-mode demo builders (beginner/advanced/expert), `scale_*` helpers |
| `indicator.py` | `DotIndicator` — slide dots |
| `host.py` | `resolve_plugin`, `should_present`, `maybe_present`, `is_active`, `sync_geometry`, `prepare_after_show` — convenience accessors for the main window |

## Flow

1. App boots into the session picker (startup no longer holds onboarding).
2. User opens an onboarding-capable tab (image_compare or multi_compare) →
   `WorkspaceSessionActivatedEvent` fires.
3. The plugin probes the tab capability; if it opts in and first-run is still
   pending, `present()` shows the mode-picker overlay over that tab.
4. User picks a mode → `_handle_completed(mode_key)` dismisses the overlay and
   calls the completion callback (`startup_runtime.on_onboarding_completed`),
   which returns to `app_host`.
5. UI mode is applied (via settings) *after* the stack switch so layout sees a
   sized page; `SettingsManager.set_first_run_completed()` prevents re-show.

## Opting a tab in

A tab participates by returning `True` for `requires_first_run_onboarding`
from its `create_service(service_id, ...)`. See
`src/tabs/image_compare/service_factory.py` and
`src/tabs/multi_compare/tab.py`.

