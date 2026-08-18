# Investigation: NavigationManager for cross-section keyboard navigation

## Problem

Session Picker's keyboard navigation between sections (tab strip ↔ content area)
fails because `OverlayScrollArea` (and potentially other Qt widgets) intercept
arrow keys before our event filters can handle them.

### Root cause

Qt's `QAbstractScrollArea` (parent of `OverlayScrollArea`) has built-in
handling for arrow keys (scrolling). When a child widget has focus and an
arrow key is pressed, the event goes:

1. Child widget's `keyPressEvent` (does nothing for arrow keys)
2. Parent chain propagation
3. Reaches `OverlayScrollArea`
4. `OverlayScrollArea`'s internal event handling consumes the arrow key
5. Our event filter never sees the event

This is not a bug — it's Qt's design. `QAbstractScrollArea` is supposed to
handle arrow keys for scrolling.

### Failed attempts (6 total)

| # | Approach | Why it failed |
|---|----------|---------------|
| 1 | `_focus_create_card` with offset | Hardcoded, doesn't scale |
| 2 | `_setup_focus_chain` with `setTabOrder` | Timing: header buttons not visible during setup |
| 3 | `_handle_arrow_key` chain-based | `OverlayScrollArea` eats events before filter |
| 4 | Global filter in `EventHandler` | Contract test forbids tab imports from platform code |
| 5 | `focusNextPrevChild` + `_PageKeyboardFilter` | `OverlayScrollArea` still eats events |
| 6 | KDevelop pattern (Qt::NoFocus + _NavigationFilter) | Filter on `_page_scroll` doesn't see events from children |

### Root cause analysis

Event filters installed on `OverlayScrollArea` or its children don't work
because `QAbstractScrollArea` intercepts arrow keys BEFORE the filter runs.
The filter is called AFTER the widget's own event handling, not before.

## Solution: NavigationManager

Follow the same manager pattern as `FlyoutManager` — a process-wide singleton
that coordinates navigation between UI sections.

### Architecture

```
NavigationManager (singleton)
├── register(section: NavigationSection)
├── unregister(section)
├── eventFilter on QApplication — catches arrow keys globally
├── policy: ExclusiveNavigationPolicy (one section active at a time)
└── each section implements NavigationSection protocol:
    ├── owns(widget: QWidget) → bool
    ├── navigate(key: int, widget: QWidget) → bool
    ├── focus_first() → bool
    └── focus_last() → bool
```

### NavigationSection protocol

```python
class NavigationSection(Protocol):
    def owns(self, widget: QWidget) -> bool:
        """True if this section owns the focused widget."""
        ...
    
    def navigate(self, key: int, widget: QWidget) -> bool:
        """Handle arrow key navigation. Returns True if handled."""
        ...
    
    def focus_first(self) -> bool:
        """Focus the first widget in this section. Returns True if successful."""
        ...
    
    def focus_last(self) -> bool:
        """Focus the last widget in this section. Returns True if successful."""
        ...
```

### NavigationManager implementation

```python
class NavigationManager(QObject):
    _instance: NavigationManager | None = None
    
    @classmethod
    def get_instance(cls) -> NavigationManager:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def __init__(self):
        super().__init__()
        self._sections: list[NavigationSection] = []
        self._event_filter_installed = False
    
    def register(self, section: NavigationSection) -> None:
        if section not in self._sections:
            self._sections.append(section)
            self._install_event_filter()
    
    def unregister(self, section: NavigationSection) -> None:
        self._sections.remove(section)
        if not self._sections:
            self._uninstall_event_filter()
    
    def _install_event_filter(self) -> None:
        if self._event_filter_installed:
            return
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)
            self._event_filter_installed = True
    
    def _uninstall_event_filter(self) -> None:
        if not self._event_filter_installed:
            return
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
            self._event_filter_installed = False
    
    def eventFilter(self, obj, event) -> bool:
        if event.type() != QEvent.Type.KeyPress:
            return False
        
        key = event.key()
        if key not in (Key_Down, Key_Up, Key_Left, Key_Right):
            return False
        
        focused = QApplication.focusWidget()
        if focused is None:
            return False
        
        # Find which section owns the focused widget
        for section in self._sections:
            if section.owns(focused):
                if section.navigate(key, focused):
                    return True
        
        return False
```

### SessionPickerSection

```python
class SessionPickerSection:
    def __init__(self, page: SessionPickerWidget):
        self._page = page
    
    def owns(self, widget: QWidget) -> bool:
        return self._page.isAncestorOf(widget) or widget is self._page
    
    def navigate(self, key: int, widget: QWidget) -> bool:
        cards = self._page._card_entries()
        card_idx = next((i for i, (_, c) in enumerate(cards) if c is widget), None)
        
        if key in (Key_Down, Key_Right):
            if card_idx is None:
                if cards:
                    cards[0][1].setFocus(Qt.FocusReason.OtherFocusReason)
                    return True
            elif card_idx < len(cards) - 1:
                cards[card_idx + 1][1].setFocus(Qt.FocusReason.OtherFocusReason)
                return True
            return False
        
        if key in (Key_Up, Key_Left):
            if card_idx is None:
                return False
            if card_idx > 0:
                cards[card_idx - 1][1].setFocus(Qt.FocusReason.OtherFocusReason)
                return True
            # At first card → exit to tab strip
            return False
        
        return False
    
    def focus_first(self) -> bool:
        cards = self._page._card_entries()
        if cards:
            cards[0][1].setFocus(Qt.FocusReason.OtherFocusReason)
            return True
        return False
    
    def focus_last(self) -> bool:
        cards = self._page._card_entries()
        if cards:
            cards[-1][1].setFocus(Qt.FocusReason.OtherFocusReason)
            return True
        return False
```

### TabStripSection

```python
class TabStripSection:
    def __init__(self, tab_bar: QWidget):
        self._tab_bar = tab_bar
    
    def owns(self, widget: QWidget) -> bool:
        return self._tab_bar.isAncestorOf(widget) or widget is self._tab_bar
    
    def navigate(self, key: int, widget: QWidget) -> bool:
        # Let the tab bar handle its own navigation (Left/Right between tabs)
        # Down → exit to session picker
        if key in (Key_Down, Key_Right):
            return False  # → next section
        if key in (Key_Up, Key_Left):
            return False  # → previous section
        return False
    
    def focus_first(self) -> bool:
        self._tab_bar.setFocus(Qt.FocusReason.OtherFocusReason)
        return True
    
    def focus_last(self) -> bool:
        self._tab_bar.setFocus(Qt.FocusReason.OtherFocusReason)
        return True
```

### Bootstrap

```python
# In ApplicationContext.initialize() or MainWindowStartupRuntime.bootstrap_main_app():
from core.navigation import NavigationManager, SessionPickerSection, TabStripSection

manager = NavigationManager.get_instance()
manager.register(SessionPickerSection(session_picker_page))
manager.register(TabStripSection(workspace_tab_strip))
```

## Key design decisions

1. **App-wide event filter** — `NavigationManager` installs its filter on
   `QApplication`, catching events BEFORE any widget-specific handling.
   This solves the `OverlayScrollArea` problem fundamentally.

2. **Section owns responsibility** — Each section decides how to navigate
   internally. The manager only routes, it doesn't know about cards, tabs,
   or panels.

3. **`owns()` check** — Simple parent-chain walk to determine which section
   owns the focused widget. Fast, no registration overhead.

4. **`navigate()` returns bool** — If a section handles the event, it returns
   True and the manager stops. If not, the manager tries the next section.

5. **No `focusNextPrevChild`** — We don't use Qt's built-in focus traversal
   for cross-section navigation. Each section handles its own focus logic.

6. **Follows FlyoutManager pattern** — Singleton, register/unregister,
   app-wide event filter, pluggable sections. Consistent with codebase.

## Files to create/modify

| File | Change |
|------|--------|
| `src/core/navigation.py` | New: `NavigationManager`, `NavigationSection` protocol |
| `src/core/navigation_sections.py` | New: `SessionPickerSection`, `TabStripSection` |
| `src/core/bootstrap.py` | Modify: register sections after bootstrap |
| `src/tabs/session_picker/widget.py` | Modify: remove `_NavigationFilter`, `_navigate`, `_find_tab_strip` |
| `src/tabs/session_picker/recent/header_bar.py` | Keep `Qt::NoFocus` on header buttons |
| `tests/test_navigation_manager.py` | New: unit tests for NavigationManager |

## Verification

After implementation:
- `./launcher.sh test tests/contracts -q` — architecture dogmas
- `./launcher.sh test src/tabs/session_picker/tests/ -q` — session picker tests
- Manual: `./launcher.sh run --ui-inspector --debug` — verify arrow navigation
