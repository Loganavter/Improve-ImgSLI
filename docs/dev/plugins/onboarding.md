# Onboarding plugin

First-run UI-mode picker: a full-window overlay mounted on the main-window
startup stack that walks the user through the available UI modes (beginner /
advanced / expert) and applies the chosen mode.

Source: `src/plugins/onboarding/`. Plugin system: [PLUGINS.md](../PLUGINS.md).

## Wiring

`@plugin(name="onboarding", startup_tier="bootstrap")`. No contribution
interfaces.

- `initialize(context)` stores `store`, `settings_manager`, `event_bus`.
- `bind_window_shell(window_shell)` resolves the main window and registers
  itself as `window.onboarding_host`.
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

1. Host checks `should_present()` (first run).
2. `present()` shows the mode-picker overlay on the startup stack.
3. User picks a mode → `_handle_completed(mode_key)` dismisses the overlay and
   calls the host's `on_completed` callback; the host reveals `app_host`.
4. UI mode is applied (via settings) *after* the stack switch so layout sees a
   sized page.
