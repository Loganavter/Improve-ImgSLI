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
2. **`NavigationManager.eventFilter()` only intercepted Up/Down arrows** —
   Enter and Escape were never routed to `_FlyoutNavigationSection.navigate()`,
   falling through to `controller.py` (selection clear) or being swallowed by
   `WA_ShowWithoutActivating`.
3. **`_FlyoutNavigationSection.navigate()` consumed arrows without delivering
   them** — returned `True` for Up/Down but didn't call `_navigate_rows()`,
   so "consumed (no movement)" happened.

### What was done

1. Flyouts register as `NavigationSection` via `_register_nav_section()` in
   `BaseFlyout.show()`, unregister in `hide()`.
2. `_FlyoutNavigationSection.owns()` claim-its the flyout and descendants.
3. `_FlyoutNavigationSection.navigate()` creates a synthetic `QKeyEvent` and
   delivers it directly to the flyout's `keyPressEvent()`.  This bypasses
   `WA_ShowWithoutActivating` which prevents Qt from routing keyboard events
   to the widget normally.  All handled keys (arrows, Enter, Escape) are
   consumed by the section so NavigationManager doesn't try cross-section
   navigation.
4. `NavigationManager.eventFilter()` expanded to intercept Enter/Escape in
   addition to Up/Down arrows.  Enter/Escape are only consumed if a section's
   `navigate()` returns `True` — no fallback consume (unlike arrows).
5. `_grab_focus()` weakens StrongFocus ancestors, stores them in
   `self._weakened_focus_ancestors`. No timers. Restoration happens in
   `_restore_focus_policies()`, called from `_finish_hide()` — ancestors
   keep `NoFocus` until the flyout is actually hidden.
6. Added `keyPressEvent` to ContextMenu: Enter (activate row), Escape (close),
   Up/Down (navigate rows).
7. Added `_navigate_rows()` to ContextMenu.

### What still doesn't work

| Issue | Status |
|-------|--------|
| Focus ring on flyout items | **No ring** — ContextMenu is not a Button subclass, has no `FocusLayer` |
| `WA_ShowWithoutActivating` blocks normal Qt event routing | **Worked around** — synthetic key delivery via navigation section |

### Analysis

Two independent problems blocked flyout keyboard navigation:

1. **`NavigationManager` only intercepted Up/Down arrows** — Enter and Escape
   were never routed to `_FlyoutNavigationSection.navigate()`.  They went
   through normal Qt routing where `WA_ShowWithoutActivating` blocked them,
   so Escape fell through to `controller.py` (selection clear).

2. **`_FlyoutNavigationSection.navigate()` consumed arrows without delivering
   them** — returned `True` for Up/Down but didn't call `_navigate_rows()`,
   so "consumed (no movement)" happened.

**Fix:**
- `NavigationManager.eventFilter()` expanded to intercept Enter/Escape via
  `_FLYOUT_KEYS`.  Enter/Escape are only consumed if a section's `navigate()`
  returns `True` — no fallback consume (unlike arrows).
- `_FlyoutNavigationSection.navigate()` creates a synthetic `QKeyEvent` and
  calls `self._flyout.keyPressEvent(event)` directly, bypassing
  `WA_ShowWithoutActivating` entirely.

### What remains

1. **Focus ring for ContextMenu** — needs `FocusLayer` integration or a
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
| `ui/managers/navigation_manager.py` | Removed parent-chain fallback in `owns()`, expanded key filter to intercept Enter/Escape for flyout sections |
| `ui/widgets/composite/base_flyout/lifecycle.py` | `_grab_focus()` no timers, `_restore_focus_policies()`, `_register_nav_section()`, `_FlyoutNavigationSection` |
| `ui/widgets/composite/context_menu/menu.py` | `StrongFocus`, `keyPressEvent` (Enter/Escape/Up/Down), `_navigate_rows()` |

---

## Conclusions

1. **CSD title bar navigation works** — buttons are reachable, Left/Right
   navigates between them, `setFocusProxy` + event filter handles focus.
2. **Shelf navigation is clean** — header ↔ content routing in base
   `ShelfWidget`, delegation from session picker.
3. **Flyout keyboard navigation works** — section registration, `owns()`,
   and synthetic key delivery via `navigate()` → `keyPressEvent()` bypass
   `WA_ShowWithoutActivating`.  Up/Down navigates rows, Enter activates,
   Escape closes.
4. **`NavigationManager` parent-chain fallback removed** — it incorrectly
   claimed overlay widgets. Flyouts now register their own sections.
5. **`QTimer.singleShot` hack removed** — weakened ancestors are stored on
   the flyout instance and restored in `_finish_hide()`. No deferred
   restoration, no race conditions.
