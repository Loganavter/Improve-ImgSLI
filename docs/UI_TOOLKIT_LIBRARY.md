# UI Toolkit Library

`packages/sli-ui-toolkit` is a reusable PyQt6 UI library.

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
    AdaptiveLabel,
    BodyLabel,
    CaptionLabel,
    ClickableLabel,
    CompactLabel,
    GenericWorker,
    GroupTitleLabel,
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

> **Note:** For a comprehensive reference of all available classes, methods, and low-level modules, please refer to the **`packages/sli-ui-toolkit/README.md`** and the technical documentation located in **`packages/sli-ui-toolkit/docs`**.

## Styling Contract

Toolkit widgets should use standard Qt geometry APIs and Qt dynamic properties for styling.

```python
button.setFixedSize(44, 44)
button.setProperty("variant", "primary")
button.setProperty("accentColor", QColor("#00BEEF"))
```

Supported style properties are intentionally generic: `variant`, `tone`, `density`, `shape`, `accentColor`, `backgroundColor`, `foregroundColor`, `iconSizePx`, etc.

For custom-painted widgets, `read_widget_style()` is the bridge between Qt properties and painter state.

> **Note:** Detailed specifications for each property and a list of supported values for specific widgets can be found in the **`packages/sli-ui-toolkit/docs/styling.md`** (or relevant doc files).

## Boundary Rules

Code inside `packages/sli-ui-toolkit/src/sli_ui_toolkit` must not import application packages such as `core`, `domain`, `features`, `ui`, or `services`. It also must not directly depend on application concepts such as store objects, viewport state, or document state.

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
from sli_ui_toolkit.widgets import UnifiedIconButton, ButtonMode

button = UnifiedIconButton("magnifier", mode=ButtonMode.TOGGLE)
button.setProperty("variant", "primary")
button.setProperty("accentColor", QColor("#00BEEF"))
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

For more implementation details, check the internal documentation in **`packages/sli-ui-toolkit/docs`**.