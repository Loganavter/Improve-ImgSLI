# Critical Analysis: Session Picker Navigation

## Timeline of Attempts

### Phase 1: Debug Logging (successful)
Added structured debug logging for routing, focus, keyboard state.

| File | What was added |
|------|---------------|
| `app_event_handler.py` | `[via=WidgetType]` in FOCUS/KEY logs |
| `router.py` | `[kbd-route]` for keyboard routing decisions |
| `keyboard_state_service.py` | `_log_state()` — press/release/reset |
| `csd_menu_strip.py` | `[csd-menu]` for flyout open/close/dispatch |
| `panel.py` | `[shelf-nav]` for shelf navigation |
| `widget.py` | `[picker-nav]` for session picker navigation |
| `lifecycle.py` | `[layout-tree]` for window widget tree dump |

**Verdict: ✅ Working.** Debug output is clear and actionable.

### Phase 2: Widget Weight Reduction (successful)
Refactored shelf widget, removed dead code, reduced panel.py from 918→573 lines.

| Change | Lines saved |
|--------|-----------|
| `panel.py` → `use_cases/sizing.py` | ~268 |
| `glass_hud/panel_display.py` RHI removal | ~217 |
| `panel.py` test alias removal | ~60 |
| `OutputPathSection.apply_to()` | ~16 |
| `shelf/widget.py` duplicate inspect_spec | ~12 |

**Verdict: ✅ Working.** All tests pass.

### Phase 3: Keyboard Navigation (FAILED — 6 attempts)

#### Attempt 1: `_focus_create_card` with offset logic
- Custom method to move focus between cards
- Problem: hardcoded, doesn't scale, header/recent items handled separately

#### Attempt 2: `_setup_focus_chain` with `setTabOrder`
- Auto-discover focusable widgets via BFS
- Problem: header buttons not visible during setup (timing issue)
- **Root cause discovered via debug logs:** `records=0 layout_ready=False header_visible=False` on first setup

#### Attempt 3: `_handle_arrow_key` chain-based navigation
- Custom chain of focusable widgets
- Problem: `OverlayScrollArea` eats arrow keys before filter sees them
- **Root cause discovered via debug logs:** Event goes Button → _OpaqueFillWidget → QWidget → OverlayScrollArea, filter on `_page_scroll` doesn't catch it

#### Attempt 4: Global filter in `EventHandler`
- App-level event filter for all arrow keys
- Problem: contract test forbids importing tab packages from platform code
- **Root cause:** `test_platform_file_does_not_import_tab_package_directly` failed

#### Attempt 5: `focusNextPrevChild` + `_PageKeyboardFilter`
- Standard Qt focus traversal mechanism
- Problem: `OverlayScrollArea` still eats events, tab strip navigation broken
- **Root cause:** Filter on `_page_scroll` doesn't see events from children

#### Attempt 6: KDevelop pattern — `_NavigationFilter` + `Qt::NoFocus`
- Action-based routing, explicit focus placement
- Problem: Filter on `_page_scroll` doesn't catch events from cards
- **Root cause:** Events go through parent chain, not through `_page_scroll`

## Root Causes Identified

### 1. `OverlayScrollArea` eats arrow keys
`QAbstractScrollArea` (parent of `OverlayScrollArea`) has built-in handling for arrow keys (scrolling). It consumes these events before they reach our filters.

**Evidence from logs:**
```
KEY Down(0x1000015) → Button → _OpaqueFillWidget → QWidget → OverlayScrollArea [via=OverlayScrollArea]
```
No filter log appears — OverlayScrollArea consumed the event.

### 2. Event filter placement problem
- Filter on `_page_scroll` (OverlayScrollArea): doesn't see events from children because events go through parent chain, not through siblings
- Filter on `SessionPickerWidget`: doesn't see events from children because OverlayScrollArea sits between them
- Filter on both: partially works but creates complexity

### 3. No mechanism for cross-section navigation
- Session picker is self-contained widget
- Tab strip is separate widget
- No shared navigation coordinator
- Each handles its own keyboard events independently

## What Actually Works

### Within session picker (Down navigation)
```
Down → SessionPickerWidget → _navigate() → first card
Down → card → _navigate() → next card
```
This works because the filter on `SessionPickerWidget` catches events from itself.

### Within session picker (Up navigation)
```
Up → card → _navigate() → previous card
Up → first card → _navigate() → tab strip
```
This works IF the filter catches the event. The problem is that when a card has focus, the event goes through OverlayScrollArea which eats it.

## The Real Problem

The `OverlayScrollArea` is a `QAbstractScrollArea` subclass that has built-in keyboard handling for scrolling. When a child widget has focus and an arrow key is pressed, the event goes:

1. Child widget's `keyPressEvent` (does nothing for arrow keys)
2. Parent chain propagation
3. Reaches `OverlayScrollArea`
4. `OverlayScrollArea`'s internal event handling consumes the arrow key for scrolling
5. Our filter never sees the event

This is a fundamental Qt issue: `QAbstractScrollArea` intercepts arrow keys for scrolling, preventing them from reaching event filters installed on it.

## Possible Solutions

### Option A: Disable scroll-on-arrow in OverlayScrollArea
Set `setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)` or override `keyPressEvent` in a subclass. But this breaks scrolling functionality.

### Option B: Use `event()` override instead of `eventFilter()`
Override `event()` on the OverlayScrollArea subclass to handle arrow keys before the default implementation. But we don't control `OverlayScrollArea`.

### Option C: Install filter on viewport, not scroll area
The viewport widget inside `OverlayScrollArea` receives events before the scroll area. Install the filter on the viewport instead. But the viewport might not exist until the scroll area is shown.

### Option D: Use Qt::WA_TransparentForMouseEvents
Set this attribute on `OverlayScrollArea` so it doesn't intercept keyboard events. But this might break mouse interaction.

### Option E: Subclass OverlayScrollArea
Override `keyPressEvent` to call our navigation logic instead of scrolling. Cleanest solution but requires changing the toolkit widget.

### Option F: Give up on arrow key navigation within session picker
Only use Tab/Shift+Tab for focus traversal. Arrow keys are handled by each widget individually. This is how many Qt apps work.

## Recommendation

**Stop adding code.** The navigation rabbit hole has consumed too much time. The debug logging (Phase 1) and widget weight reduction (Phase 2) were successful. The navigation (Phase 3) has failed repeatedly because of a fundamental Qt issue with `QAbstractScrollArea`.

**Next steps:**
1. Revert the navigation changes in `widget.py` (keep debug logging)
2. File a proper investigation into `OverlayScrollArea` keyboard handling
3. Consider Option E (subclass) or Option F (give up on arrow navigation) as a separate task
