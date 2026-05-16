# SLI UI Toolkit

`sli-ui-toolkit` is a reusable PyQt6 widget and UI-support library.

App-specific behavior (icons, translations, theme palettes, overlay layers) is injected through configuration hooks at startup.

The package provides:

1. Reusable PyQt primitives: buttons, labels, line edits, sliders, dialog shells, scrollbars, toasts, workers, theme helpers, tooltip helpers.
2. A full i18n system with JSON-based translation loading, language caching, and dotted-key resolution.
3. Higher-level composite widgets adaptable to any host app through configuration hooks.

## Start Here

Use these import layers on purpose:

- `sli_ui_toolkit`: small, stable top-level surface for common app bootstrap helpers.
- `sli_ui_toolkit.widgets`: the main public widget catalog.
- `sli_ui_toolkit.i18n`: full i18n system (TranslationManager, tr(), configure_i18n).
- `sli_ui_toolkit.managers`: flyout and timer helpers.
- `sli_ui_toolkit.icons`: icon configuration and lookup.
- `sli_ui_toolkit.theme`: theme manager.
- `sli_ui_toolkit.services`: window prewarm helpers.

If you are building UI in the app, most of the time you want `sli_ui_toolkit.widgets`.

## Configuration Hooks

App-specific integrations are supplied through configuration hooks:

- `configure_icon_resolver(...)` — icon resolution
- `configure_toolkit(...)` — overlay layers, drag-drop services, timing constants
- `configure_i18n(i18n_root=...)` — path to JSON translation files

## Quick Start

### 1. Bootstrap theme, icons, and global tooltips

```python
from pathlib import Path

from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout
from PyQt6.QtGui import QColor

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit import configure_i18n, configure_toolkit, FlyoutTimingConfig
from sli_ui_toolkit.widgets import (
    CustomButton,
    ToggleIconButton,
    install_application_tooltips,
)

app = QApplication([])

theme = ThemeManager.get_instance()
theme.register_palettes(
    light_palette={
        "Window": "#F4F4F4",
        "WindowText": "#111111",
        "Text": "#111111",
        "Base": "#FFFFFF",
        "Button": "#EAEAEA",
        "ButtonText": "#111111",
        "ToolTipBase": "#202020",
        "ToolTipText": "#FFFFFF",
        "Highlight": "#3A7AFE",
        "HighlightedText": "#FFFFFF",
        "accent": "#3A7AFE",
    },
    dark_palette={
        "Window": "#191919",
        "WindowText": "#F2F2F2",
        "Text": "#F2F2F2",
        "Base": "#222222",
        "Button": "#2B2B2B",
        "ButtonText": "#F2F2F2",
        "ToolTipBase": "#202020",
        "ToolTipText": "#FFFFFF",
        "Highlight": "#6CA6FF",
        "HighlightedText": "#FFFFFF",
        "accent": "#6CA6FF",
    },
)
theme.register_qss_path(str(Path("resources/qss/app.qss")))
theme.set_theme("dark", app)

install_application_tooltips(app)

configure_toolkit(
    timings=FlyoutTimingConfig(
        transient_auto_hide_delay_ms=300,
        flyout_animation_duration_ms=150,
        text_settings_flyout_animation_duration_ms=150,
    ),
    overlay_resolver=lambda widget: getattr(widget.window(), "overlay_layer", None),
)

configure_i18n(
    i18n_root=Path("resources/i18n"),  # directory with en/, ru/, etc. subdirs of .json files
)

window = QWidget()
layout = QVBoxLayout(window)

save_button = CustomButton(None, "Save")
save_button.setProperty("class", "primary")
save_button.setToolTip("Save current document")

magnifier_button = ToggleIconButton("magnifier")
magnifier_button.setToolTip("Toggle magnifier")

layout.addWidget(save_button)
layout.addWidget(magnifier_button)
window.show()

app.exec()
```

### 2. Configure icon resolution once

Most icon-capable toolkit widgets accept either a raw icon name string or an app-specific icon enum/value.

If your app uses its own icon enum, configure the resolver once:

```python
from sli_ui_toolkit.icons import configure_icon_resolver

configure_icon_resolver(
    resolver=lambda icon_enum: my_icon_service.get_icon(icon_enum.value),
    named_icons={
        "magnifier": MyAppIcon.MAGNIFIER,
        "settings": MyAppIcon.SETTINGS,
        "save": MyAppIcon.SAVE,
    },
)
```

After that, toolkit widgets can use semantic names like `"magnifier"` instead of hardcoding file paths.

## Which Button Should I Use?

Use this rule of thumb:

- `CustomButton`: text button, primary/secondary dialog actions, browse buttons.
- `IconButton`: one-shot icon action button.
- `SimpleIconButton`: minimal icon-only button with simple click semantics.
- `ToggleIconButton`: on/off icon action.
- `ScrollableIconButton`: icon button with wheel-driven numeric value.
- `ToggleScrollableIconButton`: toggle + wheel-adjustable value in one control.
- `LongPressIconButton`: separate short-click and long-press actions.
- `ToolButtonWithMenu`: one icon button that opens a choice menu.
- `InstancesCounterButton`: segmented add/remove counter button.
- `UnifiedIconButton`: low-level flexible icon control if you need to compose behavior yourself through `ButtonMode`.

Example:

```python
from sli_ui_toolkit.widgets import (
    ButtonType,
    IconButton,
    LongPressIconButton,
    ToggleScrollableIconButton,
)

settings_btn = IconButton("settings", ButtonType.DEFAULT)
clear_btn = LongPressIconButton("delete", ButtonType.DELETE)
split_btn = ToggleScrollableIconButton("vertical_split", "horizontal_split", min_val=0, max_val=20)
```

## ComboBox

`ComboBox` is a custom-painted combo box, not a thin `QComboBox` subclass. It currently supports the main list-management and selection methods most code expects:

- `addItem(text, userData=None)`
- `addItems(texts)`
- `insertItem(index, text, userData=None)`
- `removeItem(index)`
- `clear()`
- `count()`
- `currentIndex()`, `setCurrentIndex(index)`
- `currentText()`, `setCurrentText(text)`
- `currentData()`, `setCurrentData(data)`
- `itemText(index)`, `setItemText(index, text)`
- `itemData(index)`, `setItemData(index, data)`
- `findText(text)`, `findData(data)`
- `setMaxVisibleItems(count)`
- `setMinimumContentsLength(count)`

Signals:

- `currentIndexChanged(int)`
- `currentTextChanged(str)`

If you need the full Qt model/view `QComboBox` API, this widget does not provide that contract yet.

## Editable Text

If you want consistent line-edit behavior, prefer:

- `CustomLineEdit` for normal editable text fields.
- `apply_editable_text_behavior(widget)` if you already have a raw `QLineEdit`.

The helper normalizes focus-loss behavior and removes focus on `Enter`.

## Flyouts, Dialog Shells, and Panels

Generic reusable composites:

- `BaseFlyout`: base for anchored flyout widgets.
- `SimpleOptionsFlyout`: simple flyout of clickable options.
- `SidebarDialogShell`: sidebar + stacked pages shell for settings dialogs.
- `ScrollableDialogPage`: ready-made scrollable page for dialog content.
- `DialogActionBar`: primary/secondary action row.
- `DirectoryPickerRow`: line edit + browse button row.
- `FavoritePathActions`: paired favorite-path action buttons.
- `OutputPathSection`: bundled output-directory + filename section.
- `LogConsoleWidget`: read-only themed console for app messages.
- `ProcessConsoleWidget`: `QProcess`-driven console for real command output.
- `ToastManager` / `ToastNotification`: transient notification UI.

`ProcessConsoleWidget` is useful for embedding a live process view into the app, but it is not a full PTY/xterm replacement. It is a process console, not a terminal emulator.

Example:

```python
from PyQt6.QtWidgets import QLabel
from sli_ui_toolkit.widgets import SidebarDialogShell, ScrollableDialogPage, DialogActionBar

shell = SidebarDialogShell()

general_page = ScrollableDialogPage()
general_page.content_layout.addWidget(QLabel("General settings"))

advanced_page = ScrollableDialogPage()
advanced_page.content_layout.addWidget(QLabel("Advanced settings"))

shell.sidebar.set_nav_items([
    ("General", None),
    ("Advanced", None),
])
shell.pages_stack.addWidget(general_page)
shell.pages_stack.addWidget(advanced_page)

actions = DialogActionBar("Save", "Cancel")
shell.content_layout.addWidget(actions)
```

## Data Visualization Widgets

### SunburstChartWidget

A generic sunburst/donut chart built on `QGraphicsView`/`QGraphicsScene`.

```python
from sli_ui_toolkit.widgets import SunburstChartWidget, SunburstSegmentData
import math

chart = SunburstChartWidget()
chart.set_segments([
    SunburstSegmentData(start_angle=0, span_angle=math.pi, inner_radius=0.4, outer_radius=0.8, color=QColor("steelblue"), segment_id="a"),
    SunburstSegmentData(start_angle=math.pi, span_angle=math.pi, inner_radius=0.4, outer_radius=0.8, color=QColor("coral"), segment_id="b"),
], center_text="Total", center_sub_text="100%")
```

Signals: `segment_clicked(str, int)`, `segment_hover_enter/move/leave`.

### CalendarWidget

A three-level calendar (days / months / years) with `QStackedWidget`.

```python
from sli_ui_toolkit.widgets import CalendarWidget, CalendarViewModel, CalendarDayInfo

calendar = CalendarWidget(accent_color="#3A7AFE")
calendar.date_clicked.connect(on_date_selected)
calendar.update_view(CalendarViewModel(
    current_year=2026, current_month=5, view_mode="days",
    navigation_title="May 2026",
    days=[CalendarDayInfo(date=QDate(2026, 5, d), is_available=True, is_in_current_month=True) for d in range(1, 32)],
))
```

Signals: `date_clicked(QDate)`, `month_selected(int, int)`, `year_selected(int)`, `navigate_previous/next`, `title_clicked`.

### TimelineWidget

A generic keyframe timeline with thumbnail strip, grouped tracks, ruler, playhead, zoom/scroll, and range selection. App-specific behavior is injected via `TimelineCallbacks`.

```python
from sli_ui_toolkit.widgets import TimelineWidget, TimelineCallbacks

callbacks = TimelineCallbacks(
    should_show_track=my_track_filter,
    visible_channels=my_channel_filter,
    is_track_active=my_activity_checker,
    localize_token=my_i18n_fn,
    localize_value=my_value_formatter,
    prominent_track_ids={"splitter.main.position"},
)
timeline = TimelineWidget(callbacks=callbacks)
timeline.set_data(snapshots, fps=60, timeline_model=model, duration=10.0)
timeline.headMoved.connect(on_frame_changed)
```

Callback hooks (all optional, sensible defaults provided):
- `should_show_track(track) -> bool` — filter which tracks are visible
- `visible_channels(track) -> list[channel]` — filter which channels are shown per track
- `is_track_active(track, channel, timestamp) -> bool` — per-keyframe activity check
- `localize_token(str) -> str` — translate channel/value labels
- `localize_value(value) -> str` — format keyframe values for tooltips

Signals: `headMoved(int)`, `deletePressed()`, `zoomChanged()`, `viewportChanged()`, `resized()`.

## Managers and Services

From `sli_ui_toolkit.managers`:

- `ThemeManager`: palette + QSS application.
- `DelayedActionTimer`: thin single-shot delayed callback wrapper.
- `AnchoredFlyoutAutoHide`: auto-hide helper for flyouts anchored to a widget.
- `FlyoutManager`: singleton that keeps only one managed flyout active at a time.

From `sli_ui_toolkit.services`:

- `prewarm_widget_window(app, widget)`: show/hide offscreen once to warm rendering/layout.
- `prewarm_widget_window_once(app, widget)`: same, but idempotent per widget.
- `OffscreenPrewarmAware`: optional protocol for widgets that need prewarm hooks.

From `sli_ui_toolkit.workers` via top-level exports:

- `GenericWorker`
- `WorkerSignals`

Example:

```python
from PyQt6.QtCore import QThreadPool
from sli_ui_toolkit import GenericWorker

def load_data():
    return expensive_call()

worker = GenericWorker(load_data)
worker.signals.result.connect(handle_result)
worker.signals.error.connect(handle_error)
QThreadPool.globalInstance().start(worker)
```

## Global Tooltips

The toolkit provides application-level custom tooltips:

```python
from sli_ui_toolkit import (
    application_tooltips_enabled,
    install_application_tooltips,
    set_application_tooltips_enabled,
)

install_application_tooltips(app)
set_application_tooltips_enabled(True)
```

Current default behavior:

- custom tooltip rendering is installed globally;
- tooltip display is delayed by `500 ms`;
- hiding on leave/press is immediate.

## Public API Map

Top-level `sli_ui_toolkit` intentionally exports a small subset:

- logging helpers
- path/file helpers
- `ThemeManager`
- worker primitives
- common label widgets
- tooltip toggles
- style-bridge helpers

For the full widget catalog, use `sli_ui_toolkit.widgets`.

For the full categorized inventory, see [docs/API_CATALOG.md](docs/API_CATALOG.md).

For design principles, color system, geometry, and animation timing, see [docs/DESIGN_LANGUAGE.md](docs/DESIGN_LANGUAGE.md).

## Recommended Import Policy

Use these rules in application code:

- Import from `sli_ui_toolkit.widgets` for public widgets.
- Import from `sli_ui_toolkit.managers` for flyout/timer/theme helpers.
- Import from `sli_ui_toolkit.icons` for icon integration.
- Import from `sli_ui_toolkit.services` for prewarm helpers.
- Avoid importing deep internal modules unless the public surface is missing something you explicitly need.

## Maintaining the Toolkit

When adding documentation for a new widget or manager:

1. Export it from the appropriate public module if it is meant for app use.
2. Add a one-line description to `docs/API_CATALOG.md`.
3. Mark it clearly as either generic or app-coupled.
4. Add a minimal usage snippet if the API is not obvious from the constructor.
