# UI Toolkit Library

`sli-ui-toolkit` is a reusable, versioned PyQt6 UI library used by Improve-ImgSLI and Tkonverter.

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
button.setProperty("variant", "primary")
button.setProperty("accentColor", QColor("#00BEEF"))
```

Supported style properties are intentionally generic: `variant`, `tone`, `density`, `shape`, `accentColor`, `backgroundColor`, `foregroundColor`, `iconSizePx`, etc.

For custom-painted widgets, `read_widget_style()` is the bridge between Qt properties and painter state.

> **Note:** Detailed specifications for each property and a list of supported values for specific widgets live in the external `sli-ui-toolkit` documentation.

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
- `services`: widget and window lifecycle helpers.
- `theme`: palette and QSS theme management.
- `utils`: generic file and path helpers.
- `workers`: reusable Qt worker primitives.
- `widgets`: reusable labels, buttons, and composites.
- `ui.*`: lower-level implementations (widgets, managers, services).

## Example

```python
from PyQt6.QtGui import QColor
from sli_ui_toolkit.widgets import Button

button = Button("magnifier", toggle=True)
button.setProperty("variant", "primary")
button.setProperty("accentColor", QColor("#00BEEF"))
button.setUnderlineColor(QColor("#00BEEF"))
```

## Data Visualization Widgets

The toolkit includes self-contained data visualization composites:

- `SunburstChartWidget` — sunburst/donut chart.
- `CalendarWidget` — three-level calendar (days/months/years).
- `TimelineWidget` — keyframe timeline with thumbnail strip and grouped tracks.

All three accept state through plain data objects and emit signals for user interaction — no application imports required.

## Extension Rule

Before adding a module to the toolkit, verify that it:

1. Imports only Python stdlib, PyQt, and `sli_ui_toolkit` modules.
2. Does not reference application-specific state or features.
3. Accepts app-specific behavior through parameters, callbacks, or data objects.

For more implementation details, check the external toolkit documentation in **`Loganavter/sli-ui-toolkit`**.
