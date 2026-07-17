# UI Toolkit Library

`sli-ui-toolkit` is a reusable, versioned PySide6 UI library.

It contains widgets, an i18n system, styling tools, themes, icons, workers, and utilities. Application-specific behavior (such as icons, translation roots, overlay layers, and drag-and-drop logic) is injected via configuration hooks at startup. Application state, canvas logic, feature services, and plugins remain within the main application.

## What Belongs Here

Code belongs in the toolkit when it can be used in a standalone PyQt app without importing Improve-ImgSLI application modules.

Typical toolkit code includes:

- Reusable labels and buttons;
- Generic flyout, dialog, and overlay infrastructure;
- A full i18n system (JSON-based translation loading, caching, dotted-key resolution);
- Theme and icon managers;
- Worker primitives;
- File/path helpers;
- Widget style bridges and painter helpers;
- Self-contained composite widgets that accept state through signals, callbacks, or plain data objects.

## Public API

The package exposes the common entry points below at the top level:

```python
from sli_ui_toolkit import (
    ClickableLabel,
    GenericWorker,
    Label,
    LabelConfig,
    LabelVariantSpec,
    ThemeManager,
    WidgetStyleTokens,
    get_log_directory,
    get_unique_filepath,
    read_widget_style,
    resource_path,
    setup_logging,
    setup_simple_logging,
    update_widget_style,
)
```

Additional public modules are available through their package paths, including `sli_ui_toolkit.i18n`, `sli_ui_toolkit.icons`, `sli_ui_toolkit.widgets`, and others.

> **Note:** For a comprehensive reference of all available classes, methods, and low-level modules, refer to the external **`Loganavter/sli-ui-toolkit`** repository and its `docs/` directory.

## Styling Contract

Toolkit widgets should use standard Qt geometry APIs and Qt dynamic properties for styling.

```python
button.setFixedSize(44, 44)
button.setProperty("variant", "surface")
button.setProperty("accentColor", QColor("#00BEEF"))
```

Supported style properties are intentionally generic: `variant`, `tone`, `density`, `shape`, `accentColor`, `backgroundColor`, `foregroundColor`, `iconSizePx`, etc.

For custom-painted widgets, `read_widget_style()` is the bridge between Qt properties and painter state.

> **Note:** Detailed specifications for each property and a list of supported values for specific widgets live in the external `sli-ui-toolkit` documentation.

Workspace-style tab rows use the toolkit's public `AdaptiveTabStrip`.
Improve-ImgSLI supplies icons and session lifecycle callbacks; tab painting,
adaptive close-button visibility, stable tab sizing, and add-button placement
remain toolkit-owned.

Dialog content sections (e.g. video editor export tabs) use `TopTabHost` /
`TopTabBar` — the horizontal twin of sidebar `IconListWidget`, not `QTabWidget`.

## Boundary Rules

Code inside the `sli_ui_toolkit` package must not import application packages such as `core`, `domain`, `features`, `ui`, or `services`. It also must not directly depend on application concepts such as store objects, viewport state, or document state.

## Allowed Inputs

Toolkit widgets receive application behavior through:

- Constructor parameters;
- Callbacks and protocols;
- Plain dataclasses and Qt signals;
- Icons and resources passed from application code.

## Package Layout

The current package is organized around these reusable areas:

- `core`: logging helpers.
- `i18n`: full i18n system — JSON tree loading, caching, dotted-key resolution.
- `icons`: icon loading service.
- `managers`: flyout and other generic UI managers.
  Hosts own coexistence via `FlyoutManager.set_show_policy(GroupShowPolicy(...))`
  (see toolkit `FLYOUT_SYSTEM.md`); app wiring lives in `ui/flyout_policy.py`.
- `services`: widget and window lifecycle helpers.
- `theme`: palette and QSS theme management.
- `utils`: generic file and path helpers.
- `workers`: reusable Qt worker primitives.
- `widgets`: reusable labels, buttons, and composites.
- `ui.*`: lower-level implementations (widgets, managers, services).

## Example

```python
from PySide6.QtGui import QColor
from sli_ui_toolkit.widgets import Button

button = Button("magnifier", toggle=True)
button.setProperty("variant", "surface")
button.setProperty("accentColor", QColor("#00BEEF"))
button.setUnderlineColor(QColor("#00BEEF"))
```

## Data Visualization Widgets

The toolkit includes self-contained data visualization composites:

- `SunburstChartWidget` — sunburst/donut chart.
- `CalendarWidget` — three-level calendar (days/months/years).
- `TimelineWidget` — keyframe timeline with thumbnail strip and grouped tracks.

All three accept state through plain data objects and emit signals for user interaction — no application imports required.

## App-side dialog geometry (`shared_toolkit/ui/layout_sizing.py`)

Improve-ImgSLI keeps content-driven dialog sizing in the app layer (not in `sli-ui-toolkit`).

**Full guide (skeleton, CSD, crush-resistant layouts, preview sizeHints, i18n):**
[DIALOGS.md](DIALOGS.md).

Short recipe:

1. **Primitives** — `widget_width_hint`, `sum_visible_widget_height_hint`, `measure_scroll_pages_stack`, `clamp_to_screen`.
2. **Per-dialog module** — e.g. `plugins/export/layout_geometry.py`, `plugins/settings/layout_geometry.py`.
3. **Apply** — `apply_dialog_geometry` + `GeometryApplyPolicy` (`lock_minimum_to_computed` for non-scroll dialogs; `force_resize` on the **initial** finalize after CSD).
4. **Lifecycle** — `ThemedDialog.install_dialog_geometry`; deferred finalize via `QTimer.singleShot(0, …)`; `sync_csd_chrome` after programmatic resize.

Reference consumers: Export (preview + form — best template for content-locked dialogs), Settings (sidebar + scroll pages), Video editor, Help, Image properties.

## Extension Rule

Before adding a module to the toolkit, verify that it:

1. Imports only Python stdlib, PyQt, and `sli_ui_toolkit` modules.
2. Does not reference application-specific state or features.
3. Accepts app-specific behavior through parameters, callbacks, or data objects.

For more implementation details, check the external toolkit documentation in **`Loganavter/sli-ui-toolkit`**.
