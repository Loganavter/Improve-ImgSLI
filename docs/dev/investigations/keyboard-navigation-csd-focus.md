# Investigation: Keyboard Navigation, CSD Focus, and Flyout Focus Routing

## Summary

A session of debugging keyboard navigation across the app revealed several
interconnected issues: CSD title bar buttons unreachable by keyboard, flyout
widgets not receiving focus when opened, and the `NavigationManager` incorrectly
claiming overlay widgets via parent-chain `isAncestorOf` checks.

---

## Part 1: CSD Title Bar Keyboard Navigation

### Problem

All CSD title bar buttons (File/Help menu triggers, undo/redo) had
`Qt.FocusPolicy.NoFocus`, making them unreachable by keyboard. The
`NavigationManager` had no section registered for the title bar.

### What was done

1. Removed `NoFocus` from menu triggers (`csd_menu_strip.py`) and undo/redo
   buttons (`menu_controller.py`).
2. Added `TitleBarNavigationSection` in `src/ui/main_window/title_bar_navigation.py`.
3. Registered it in `startup.py` before `auto_register_from_descriptors()` so it
   sits at index 0 (topmost section).
4. Added `StrongFocus` policy, `FocusLayer`-compatible event filter, and
   `_focusable_buttons()` / `focus_first_button()` / `focus_last_button()` to
   the toolkit's `CustomTitleBar` (`widget.py`).

### Issue: `setFocus()` on child buttons fails

Qt's focus chain redirects `setFocus()` on a child widget to a StrongFocus
ancestor (the title bar itself). The button never gets keyboard focus.

**Attempted fixes:**

| Approach | Result |
|----------|--------|
| `setFocus()` directly | Redirected to title bar |
| `setFocusProxy(child)` | Worked for initial focus, broke on subsequent Left/Right |
| Temporarily weaken title bar to `NoFocus` | Worked but fragile |
| `_set_child_focus()` with `NoFocus` temporary | Worked but caused re-entrancy |

**Final working approach:** `setFocusProxy` + `setFocus()` on the title bar
shell. The event filter on QApplication catches Left/Right for descendant
buttons.

### Issue: `owns()` via `isAncestorOf` too broad

The `_WidgetNavigationSection.owns()` uses `isAncestorOf`, which matches
**any** descendant — including overlay scroll areas, flyout containers, etc.

**Temporary fix:** walk parent chain checking for `flyout_group` attribute or
popup window flags. This was later superseded by the flyout section registration.

---

## Part 2: NavigationManager Section Matching

### Problem

After `focus_last()` redirects focus to a child button via `setFocusProxy`,
the `NavigationManager`'s main loop calls `spec.owns(focused)` for each
section. The focused widget (button) is not directly owned by any section,
so no section claims it.

### What was done

Added a fallback in `NavigationManager.eventFilter()`: after the main loop,
walk the focused widget's parent chain to find which section owns an
ancestor.

**Issue:** The fallback incorrectly claimed overlay widgets (flyouts, popups)
that were parented inside a section's widget tree.

### Resolution

Removed the fallback. Instead, flyouts register their own `NavigationSection`
when they show (see Part 3).

---

## Part 3: Flyout Focus Routing

### Problem

When a flyout (context menu, options flyout) opens, the `NavigationManager`
doesn't switch focus to it. Arrow keys inside the flyout are not handled.
Enter/Escape don't work.

### Root causes

1. **`WA_ShowWithoutActivating`** on ContextMenu prevents window activation,
   blocking keyboard events.
2. **`_grab_focus()` restores window StrongFocus immediately** — the window
   steals focus back before the flyout can process keyPressEvent.
3. **`_FlyoutNavigationSection.navigate()` returns `True` for all keys** —
   the NavigationManager consumes the event, preventing the flyout's own
   `keyPressEvent` from firing.
4. **ContextMenu `keyPressEvent` only handles Escape with open submenu** —
   Enter, general Escape, and arrow navigation between rows not implemented.

### What was done

1. Flyouts register as `NavigationSection` via `_register_nav_section()` in
   `BaseFlyout.show()`, unregister in `hide()`.
2. `_FlyoutNavigationSection.owns()` claim-its the flyout and descendants.
3. `_FlyoutNavigationSection.navigate()` returns `True` for arrows, `False`
   for Enter/Escape (yield to flyout's own keyPressEvent).
4. `_grab_focus()` weakens StrongFocus ancestors, stores them in
   `self._weakened_focus_ancestors`. No timers. Restoration happens in
   `_restore_focus_policies()`, called from `_finish_hide()` — ancestors
   keep `NoFocus` until the flyout is actually hidden.
5. Added `keyPressEvent` to ContextMenu: Enter (activate row), Escape (close),
   Up/Down (navigate rows).
6. Added `_navigate_rows()` to ContextMenu.

### What still doesn't work

| Issue | Status |
|-------|--------|
| Focus ring on flyout items | **No ring** — ContextMenu is not a Button subclass, has no `FocusLayer` |
| Enter selects item | **Not working** — `keyPressEvent` not invoked despite focus being on ContextMenu |
| Escape closes flyout | **Intercepted** by `controller.py` (selection clear), not by ContextMenu |
| `WA_ShowWithoutActivating` blocks keyboard | **Suspected root cause** — removing breaks Wayland/QRhi |

### Analysis

The core issue remains: `WA_ShowWithoutActivating` prevents window activation.
Even though `setFocus()` grants focus to the ContextMenu, keyboard events
don't reach its `keyPressEvent` because the window is not activated.

**Timer-based `_grab_focus` was removed.** The old approach (weaken ancestors,
defer restore via `QTimer.singleShot(50)`) did not work because Qt's event
processing order meant the timer fired before any KeyPress arrived:

1. `setFocus()` → focus granted to flyout
2. Timer fires → window StrongFocus restored
3. KeyPress arrives → window has StrongFocus → focus stolen back

The new approach stores weakened ancestors on the flyout instance and restores
them in `_finish_hide()`. This guarantees the window stays weakened for the
entire lifetime of the flyout. However, the fundamental problem remains:
`WA_ShowWithoutActivating` blocks keyboard events from reaching the flyout's
`keyPressEvent` regardless of focus policy state.

### What remains

1. **Remove `WA_ShowWithoutActivating`** and accept that flyouts activate
   the window. The original comment says this is for Wayland/QRhi stability,
   but the actual issue is that keyboard navigation doesn't work at all
   without activation.

2. **Make flyouts top-level popup windows** instead of in-window overlays.
   Popups get their own activation context and keyboard events naturally.
   This is a larger architectural change.

3. **Focus ring for ContextMenu** — needs `FocusLayer` integration or a
   custom painted focus indicator on the menu rows.

---

## Part 4: Widget Weight / Architecture Notes

### Shelf navigation moved to base class

`RecentProjectsPanel.navigate()` was moved to the generic `ShelfWidget` base
class (`src/ui/widgets/shelf/widget.py`). The shelf provides:
- `navigate(key, widget)` — header ↔ content routing
- `_first_focusable(container)` — finds first StrongFocus child
- `header_host()` / `content_host()` — zone accessors

### Session picker delegation

`SessionPickerWidget._nav_navigate()` delegates to `recent.navigate(key, widget)`
for shelf widgets, keeping shelf-internal navigation in the shelf.

---

## Files Changed

### App (`src/`)

| File | Changes |
|------|---------|
| `ui/main_window/title_bar_navigation.py` | New: `TitleBarNavigationSection` |
| `ui/main_window/startup.py` | Register title bar section, debug log |
| `ui/main_window/lifecycle.py` | Initial focus fix for title bar button |
| `ui/main_window/csd_menu_strip.py` | Removed `NoFocus` from triggers |
| `ui/main_window/menu_controller.py` | Removed `NoFocus` from undo/redo |
| `core/navigation_sections.py` | Updated comments, added logging |
| `tabs/session_picker/widget.py` | Shelf delegation, logging |
| `tabs/session_picker/recent/panel.py` | Removed `navigate()` (moved to base) |
| `ui/widgets/shelf/widget.py` | Added `navigate()`, `_first_focusable()` |
| `ui/widgets/workspace_tab_strip.py` | Updated comments |

### Toolkit (`sli-ui-toolkit`)

| File | Changes |
|------|---------|
| `ui/windows/custom_title_bar/widget.py` | `StrongFocus`, event filter, `_focusable_buttons()`, `_set_child_focus()` |
| `ui/managers/navigation_manager.py` | Removed parent-chain fallback in `owns()` |
| `ui/widgets/composite/base_flyout/lifecycle.py` | `_grab_focus()` no timers, `_restore_focus_policies()`, `_register_nav_section()`, `_FlyoutNavigationSection` |
| `ui/widgets/composite/context_menu/menu.py` | `StrongFocus`, `keyPressEvent` (Enter/Escape/Up/Down), `_navigate_rows()` |

---

## Conclusions

1. **CSD title bar navigation works** — buttons are reachable, Left/Right
   navigates between them, `setFocusProxy` + event filter handles focus.
2. **Shelf navigation is clean** — header ↔ content routing in base
   `ShelfWidget`, delegation from session picker.
3. **Flyout focus routing is partially working** — section registration and
   `owns()` work, ancestor weakening is clean (no timers, restore on hide),
   but keyboard events don't reach `keyPressEvent` due to
   `WA_ShowWithoutActivating` / window activation issues.
4. **`NavigationManager` parent-chain fallback removed** — it incorrectly
   claimed overlay widgets. Flyouts now register their own sections.
5. **`QTimer.singleShot` hack removed** — weakened ancestors are stored on
   the flyout instance and restored in `_finish_hide()`. No deferred
   restoration, no race conditions.
