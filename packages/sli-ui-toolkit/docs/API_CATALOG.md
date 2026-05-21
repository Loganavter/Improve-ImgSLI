# SLI UI Toolkit — Full API Catalog

All public names are importable from `sli_ui_toolkit.widgets` unless noted otherwise.

This document is the public reference.

If you are onboarding instead of looking up a symbol, start with [../README.md](/home/jorj/Загрузки/Improve-ImgSLI/packages/sli-ui-toolkit/README.md).
If you are changing internals, also read [ARCHITECTURE.md](/home/jorj/Загрузки/Improve-ImgSLI/packages/sli-ui-toolkit/docs/ARCHITECTURE.md).

---

## Import Layers

### `from sli_ui_toolkit import ...`

Small convenience surface for app bootstrap and commonly used primitives.

Exports:

- `AdaptiveLabel`, `BodyLabel`, `CaptionLabel`, `ClickableLabel`, `CompactLabel`, `GroupTitleLabel`
- `GenericWorker`, `WorkerSignals`
- `ThemeManager`
- `TranslationManager`, `ToolkitTranslationEvents`
- `WidgetStyleTokens`, `read_widget_style`, `update_widget_style`
- `configure_i18n`, `configure_toolkit`, `FlyoutTimingConfig`
- `tr`, `get_current_language`, `emit_language_changed`, `translation_events`
- `get_log_directory`, `get_unique_filepath`, `resource_path`
- `setup_logging`, `setup_simple_logging`
- `install_application_tooltips`, `set_application_tooltips_enabled`, `application_tooltips_enabled`

### `from sli_ui_toolkit.widgets import ...`

Main public widget catalog — everything below.

---

## Atomic Widgets

### Button (unified)

A single `Button` class replaces all legacy button widgets via composable parameters.

```python
from sli_ui_toolkit.widgets import Button, ButtonGroup

# Icon-only toggle
btn = Button(AppIcon.MAGNIFIER, toggle=True)

# Icon with scroll wheel value
btn = Button(AppIcon.LINE, toggle=True, scrollable=(0, 10), show_underline=True)

# Icon pair (unchecked/checked icons)
btn = Button(icon=(AppIcon.VERTICAL, AppIcon.HORIZONTAL), toggle=True)

# Text button in dialog
btn = Button(text="Browse…", variant="surface")

# Icon + text with accent style
btn = Button(AppIcon.SAVE, text="Save", variant="accent")

# Long press support
btn = Button(AppIcon.DELETE, long_press=True, variant="delete")

# Dropdown menu
btn = Button(AppIcon.MODE, menu=[("Option A", "a"), ("Option B", "b")])

# Badge overlay
btn = Button(AppIcon.MAGNIFIER, toggle=True, badge="3")
```

**Constructor parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `icon` | icon / (icon, icon) | Single icon or (unchecked, checked) pair |
| `text` | str | Text label (with or without icon) |
| `toggle` | bool | Checkable on/off behavior |
| `scrollable` | (min, max) | Enable mouse-wheel value adjustment |
| `long_press` | bool | Emit `longPressed` after hold delay |
| `badge` | str/int | Small overlay badge text |
| `show_underline` | bool | Bottom color underline |
| `menu` | list | Dropdown menu items |
| `variant` | str | Visual variant (see below) |
| `size` | (w, h) | Fixed size |
| `parent` | QWidget | Parent widget |

**Variants:**

| Variant | Theme prefix | Border | Use case |
|---------|-------------|--------|----------|
| `"default"` | `button.toggle` | no | Toolbar toggles (default) |
| `"accent"` | `button.default` | yes, blue | Accent actions (swap, settings, help) |
| `"delete"` | `button.delete` | yes, red | Destructive actions |
| `"primary"` | `button.primary` | yes | Text buttons in main UI |
| `"surface"` | `button.dialog.default` | yes | Dialog buttons |
| `"ghost"` | transparent | no | Invisible until hovered |
| `"subtle"` | Window color | no | Blends with background |

**Signals:**

| Signal | Description |
|--------|-------------|
| `clicked` | Click or short-click (when `long_press=True`) |
| `shortClicked` | Alias for click in long-press mode |
| `toggled(bool)` | Toggle state changed |
| `valueChanged(int)` | Scroll value changed |
| `longPressed` | Long press detected |
| `rightClicked` | Right mouse button |
| `middleClicked` | Middle mouse button |
| `menuTriggered(object)` | Menu item selected (emits item data) |
| `triggered` | Alias for `menuTriggered` |

**Runtime methods:**

| Method | Description |
|--------|-------------|
| `set_color(QColor\|list\|None)` | Set underline color (e.g. from color picker) |
| `set_value(int)` / `get_value()` | Scroll value access |
| `setBadge(str)` | Update badge text |
| `set_footer_mode(bool)` | Flat top, rounded bottom (for footer buttons) |
| `set_show_strike_through(bool)` | Red diagonal strikethrough |
| `set_override_bg_color(QColor)` | Force background color |
| `set_actions(list)` | Update menu items |
| `show_menu()` | Programmatically open menu |
| `setFlyoutOpen(bool)` | Visual state for attached flyout |

**Underline scaling:** underline thickness and arc radius scale proportionally with widget height (baseline: 32 px). This ensures visibility on high-DPI / large UI modes.

### ButtonGroup

Container that groups buttons with a shared label.

```python
group = ButtonGroup([btn1, btn2, btn3], label="View")
```

### Other Button Widgets

| Widget | Description |
|--------|-------------|
| `InstancesCounterButton` | Segmented add/remove counter button. |

### Labels

| Widget | Description |
|--------|-------------|
| `AdaptiveLabel` | Label that adapts font size to fit content. |
| `BodyLabel` | Standard body-text label. |
| `CaptionLabel` | Small caption/status label. |
| `CompactLabel` | Compact label with reduced spacing. |
| `GroupTitleLabel` | Bold section title label. |
| `ClickableLabel` | Label that emits `clicked` signal. |
| `DropZoneLabel` | Label with drag-and-drop zone visuals and file accept logic. |

### Inputs

| Widget | Description |
|--------|-------------|
| `CustomLineEdit` | Themed line edit with focus normalization. |
| `CheckBox` | Custom-painted checkbox. |
| `RadioButton` | Custom-painted radio button. |
| `Slider` | Custom-painted slider with accent track. |
| `SpinBox` | Custom-painted spinbox. |
| `Switch` | Custom-painted toggle switch. |
| `ComboBox` | Full custom-painted combo box with dropdown popup, type-to-search matching, and keyboard navigation. |
| `ScrollableComboBox` | Combo box with mouse-wheel cycling. |
| `TimeLineEdit` | Time input (HH:MM) widget with underline styling. |

### Scrolling

| Widget | Description |
|--------|-------------|
| `MinimalistScrollBar` | Thin minimalist scrollbar for custom scroll areas. |
| `OverlayScrollArea` | Scroll area with overlay-style thin scrollbars. |

### Other Atomic

| Widget | Description |
|--------|-------------|
| `LoadingSpinner` | Animated conical-gradient loading spinner. |
| `CustomGroupWidget` / `CustomGroupBuilder` | Grouped widget container with builder pattern. |

---

## Composite Widgets

### Flyouts & Panels

| Widget | Description |
|--------|-------------|
| `BaseFlyout` | Base class for anchored flyout widgets. |
| `SimpleOptionsFlyout` | Flyout displaying a list of clickable text options. |
| `ColorOptionsFlyout` / `IconActionFlyout` | Flyout with icon+label action rows and optional color pickers. |
| `FlyoutIconButton` | Icon button that auto-manages an attached flyout on hover/click. |
| `IndexedToggleFlyout` | Flyout with numbered toggle slots (show/hide per instance). |
| `FontSettingsFlyout` | Flyout for font family/size/weight settings. |
| `UnifiedFlyout` | Full-featured dual-pane overlay list with drag-drop reordering, session management, animated open/close. Import: `sli_ui_toolkit.ui.widgets.composite.unified_flyout`. |

### Dialogs & Navigation

| Widget | Description |
|--------|-------------|
| `SidebarDialogShell` | Sidebar + stacked pages dialog container. |
| `ScrollableDialogPage` | Ready-made scrollable page for dialog content. |
| `DialogActionBar` | Primary/secondary action button row. |
| `SidebarNavList` / `IconListWidget` / `IconListItem` | Icon-based navigation list for sidebar shells. |
| `MarkdownHelpDialog` / `MarkdownHelpSection` | Markdown-based help/documentation dialog with anchors, generated TOC, and internal `help://slug#anchor` navigation. |

### Path & File

| Widget | Description |
|--------|-------------|
| `DirectoryPickerRow` | Line edit + browse button for directory selection. |
| `FavoritePathActions` | Paired favorite-path action buttons. |
| `OutputPathSection` | Combined output-directory + filename form section. |

### Console & Logging

| Widget | Description |
|--------|-------------|
| `LogConsoleWidget` / `LogConsoleEntry` | Read-only themed console for app log messages. |
| `ProcessConsoleWidget` | `QProcess`-driven console for live command output with stdin input. |

### Notifications

| Widget | Description |
|--------|-------------|
| `ToastManager` / `ToastNotification` | Transient notification toasts. |

### Data Visualization

| Widget | Description |
|--------|-------------|
| `SunburstChartWidget` | Sunburst/donut chart (`QGraphicsView`-based). Feed `SunburstSegmentData` list. Signals: `segment_clicked`, `segment_hover_*`. |
| `SunburstSegmentData` | Dataclass: start_angle, span_angle (radians), inner/outer radius, color, segment_id. |
| `SunburstSegmentItem` | Individual chart segment (`QGraphicsPathItem`). |
| `CalendarWidget` | Three-level calendar (days/months/years) with `QStackedWidget`. Feed `CalendarViewModel` via `update_view()`. |
| `CalendarDayButton` | Individual day button with `date_clicked`/`date_context_menu` signals. |
| `CalendarDayInfo` / `CalendarMonthInfo` / `CalendarYearInfo` | Per-cell data for calendar. |
| `CalendarViewModel` | Full calendar view state (year, month, day, view_mode, navigation). |
| `TimelineWidget` | Keyframe timeline with thumbnail strip, grouped tracks, ruler, playhead, zoom/scroll, range selection. Feed via `set_data()`. |
| `TimelineCallbacks` | Callback hooks: `should_show_track`, `visible_channels`, `is_track_active`, `localize_token`, `localize_value`, `prominent_track_ids`. |

### Drag & Drop

| Widget | Description |
|--------|-------------|
| `DragGhostWidget` | Semi-transparent ghost widget shown during drag operations. |

---

## Overlays (from `sli_ui_toolkit.ui.widgets.overlays`)

| Widget | Description |
|--------|-------------|
| `DragDropOverlay` | Transparent overlay showing drop zones during drag. |
| `PasteDirectionOverlay` | Directional paste target overlay (up/down/left/right). Signals: `direction_selected(str)`, `cancelled()`. |

---

## List Items (from `sli_ui_toolkit.ui.widgets.list_items`)

| Widget | Description |
|--------|-------------|
| `RatingItem` | Star-rating list item with interactive hover and click. |

---

## Helpers (from `sli_ui_toolkit.widgets`)

| Name | Description |
|------|-------------|
| `apply_editable_text_behavior(widget)` | Normalize QLineEdit focus/enter behavior. |
| `calculate_centered_overlay_geometry(...)` | Compute centered overlay position relative to parent. |
| `draw_bottom_underline(painter, ...)` | Draw a themed bottom underline on a widget. |
| `draw_rounded_shadow(painter, ...)` | Draw a rounded drop shadow behind a rect. |
| `UnderlineConfig` | Configuration dataclass for underline painting. |
| `WidgetStyleTokens` | Resolved style token set for custom painters. |
| `read_widget_style(widget)` | Read Qt dynamic properties into `WidgetStyleTokens`. |
| `update_widget_style(widget, tokens)` | Write `WidgetStyleTokens` back to Qt properties. |

---

## i18n System (`sli_ui_toolkit.i18n`)

| Name | Description |
|------|-------------|
| `TranslationManager` | Singleton: loads `<i18n_root>/<lang>/*.json`, merges with `en/` fallback, caches per language. |
| `configure_i18n(i18n_root=...)` | Set path to i18n directory. |
| `tr(key, language=None, default=None)` | Translate dotted key (e.g. `"dialog.save.title"`). |
| `get_current_language()` | Return currently loaded language code. |
| `translation_events()` | Return `ToolkitTranslationEvents` with `language_changed(str)` signal. |
| `emit_language_changed(lang)` | Emit language-changed signal. |

---

## Managers (`sli_ui_toolkit.managers`)

| Name | Description |
|------|-------------|
| `ThemeManager` | Palette + QSS theme application singleton. |
| `FlyoutManager` | Ensures only one registered flyout is active at a time. |
| `DelayedActionTimer` | Single-shot delayed callback wrapper. |
| `AnchoredFlyoutAutoHide` | Auto-hide helper for anchored flyouts. |

---

## Services (`sli_ui_toolkit.services`)

| Name | Description |
|------|-------------|
| `prewarm_widget_window(app, widget)` | Show/hide offscreen to warm rendering/layout. |
| `prewarm_widget_window_once(app, widget)` | Idempotent per-widget prewarm. |
| `OffscreenPrewarmAware` | Protocol for widgets needing prewarm hooks. |

---

## Workers (`sli_ui_toolkit.workers` / top-level)

| Name | Description |
|------|-------------|
| `GenericWorker` | `QRunnable`-based worker with result/error/progress signals. |
| `WorkerSignals` | Signal set (result, error, finished, progress). |

---

## Icons (`sli_ui_toolkit.icons`)

| Name | Description |
|------|-------------|
| `configure_icon_resolver(resolver=..., named_icons=...)` | Set icon resolution strategy and named icon map. |
| `resolve_icon(name_or_enum)` | Resolve an icon name/enum to QIcon. |
| `get_named_icon(name)` | Get QIcon by semantic name. |
| `get_icon_by_name(name)` / `get_icon_by_path(path)` | Direct icon lookup. |
| `get_themed_icon(name)` | Get theme-aware icon variant. |
| `IconService` | Service class for icon loading/caching. |

---

## Configuration Hooks

| Function | Module | Description |
|----------|--------|-------------|
| `configure_toolkit(timings=..., overlay_resolver=..., dragdrop_service=...)` | `sli_ui_toolkit.config` | Overlay layer resolution, drag-drop, timing constants. |
| `configure_icon_resolver(resolver=..., named_icons=...)` | `sli_ui_toolkit.icons` | Icon resolution strategy. |
| `configure_i18n(i18n_root=...)` | `sli_ui_toolkit.i18n` | Path to JSON translation directory. |

---

## Tooltip System

| Name | Description |
|------|-------------|
| `install_application_tooltips(app)` | Install global custom tooltip rendering. |
| `set_application_tooltips_enabled(bool)` | Enable/disable custom tooltips globally. |
| `application_tooltips_enabled()` | Query current tooltip state. |
| `PathTooltip` | Singleton tooltip renderer (internal, used by timeline and other widgets). |

---

## Reuse Guidance

All widgets are generic and safe for reuse in any PyQt6 application. No widget imports application-specific modules.

Safe first choices for new code:

- `Button` with appropriate `variant` — covers icons, toggles, scrollable, long-press, menus, text
- `ButtonGroup` for grouped toolbar sections
- Labels, `CustomLineEdit`
- `SidebarDialogShell` + `ScrollableDialogPage` + `DialogActionBar`
- `DirectoryPickerRow` / `OutputPathSection`
- `LogConsoleWidget` / `ProcessConsoleWidget`
- `ToastManager`
- `SunburstChartWidget` / `CalendarWidget` / `TimelineWidget`
- `ThemeManager` + tooltip helpers
- `GenericWorker`
