# SLI UI Toolkit — Design Language

## Overview

The toolkit implements a custom dark-first design language with the following principles:

- **Custom-painted controls** — all interactive widgets (checkbox, radio, slider, switch, combobox, spinbox) are painted entirely via `QPainter`, not styled via QSS.
- **Smooth animated transitions** — state changes (hover, check, toggle) use `QPropertyAnimation` with `OutCubic` easing and short durations (100–200 ms).
- **Accent-driven color** — a single accent color (from `ThemeManager`) propagates through all active/focus/selected states.
- **Dark and light themes** — two palette sets registered at startup; widgets resolve colors from the active palette at paint time.
- **Compact geometry** — controls are sized for tool-dense UIs (20 px indicators, 22 px track heights, 44 px button defaults).

## Not Fluent, Not Material

The design was originally inspired by WinUI 3 / Fluent Design but has diverged significantly:

| Aspect | Fluent Design | SLI Toolkit |
|--------|---------------|-------------|
| Elevation | Acrylic/Mica layers, shadows | Flat with minimal shadow on flyouts only |
| Motion | Spring-based, reveal highlight | Simple OutCubic property animations |
| Typography | Segoe UI Variable, type ramp | System font, 3 label sizes |
| Color | Semantic tokens, layered tints | Single accent + palette-resolved colors |
| Density | Standard/Compact modes | Single compact-density mode |
| Borders | Rounded 4 px default | 2–8 px radius depending on context |
| Iconography | Segoe Fluent Icons | App-supplied SVG icons via resolver |

The result is a pragmatic, compact, dark-first toolkit for image/video tool UIs — not a faithful Fluent implementation.

## Color System

Colors are resolved through `ThemeManager` at runtime:

```python
theme = ThemeManager.get_instance()
palette = theme.current_palette()

accent = palette.get("accent")       # Primary interactive color
window = palette.get("Window")       # Background
text = palette.get("WindowText")     # Foreground text
base = palette.get("Base")           # Input field backgrounds
button = palette.get("Button")       # Button surface
```

### Semantic QSS Tokens

QSS files use `@token` placeholders resolved at theme-apply time:

- `@accent` — primary accent
- `@dialog.text` — text in dialogs
- `@dialog.background` — dialog surfaces
- `@dialog.border` — subtle borders
- `@dialog.input.background` — input field fill
- `@flyout.background` / `@flyout.border` — flyout surfaces
- `@input.border.thin` — hairline input borders

## Typography

Three label density levels:

| Widget | Default size | Weight | Use case |
|--------|-------------|--------|----------|
| `GroupTitleLabel` | 13 px | Bold | Section headers |
| `BodyLabel` | 12 px | Normal | Body text, descriptions |
| `CaptionLabel` | 11 px | Normal | Status text, hints |
| `CompactLabel` | 10 px | Normal | Dense data displays |
| `AdaptiveLabel` | Auto-fit | Normal | Labels that resize to content |

## Control Geometry

| Control | Key dimensions |
|---------|---------------|
| `CheckBox` | 20×20 px indicator, 4 px radius |
| `RadioButton` | 20×20 px indicator, fully round |
| `Switch` | 44×22 px track, 12 px knob |
| `Slider` | 5 px track height, 7 px thumb radius |
| `SpinBox` | Standard line edit with 2 px radius |
| `ComboBox` | 8 px radius, 24 px dropdown arrow area |
| `IconButton` | 44×44 px default, 24×24 px icon |

## Animation Timing

All transitions use `QEasingCurve.Type.OutCubic`:

| Transition | Duration |
|-----------|----------|
| Hover in/out | 100–120 ms |
| Check/toggle | 150–160 ms |
| Flyout open/close | 150 ms |
| Slider thumb press | 100 ms |

## Interaction Patterns

- **Hover** — subtle brightness shift or outline emphasis.
- **Active/pressed** — accent fill or accent outline.
- **Focus** — accent border (1 px) on inputs.
- **Disabled** — reduced opacity (0.3–0.5), no hover response.

## Flyout & Overlay Pattern

Flyouts are in-window widgets (not native popups):

- Anchored to a trigger widget.
- Painted with rounded shadow (`draw_rounded_shadow`).
- Auto-hide on mouse leave with configurable delay.
- Only one flyout active at a time (`FlyoutManager`).

## Extension Guidance

When adding a new custom-painted control:

1. Inherit from the appropriate Qt base (`QWidget`, `QAbstractButton`, etc.).
2. Resolve colors from `ThemeManager.get_instance()` inside `paintEvent`.
3. Use `QPropertyAnimation` for state transitions — never `QTimer`-based manual interpolation.
4. Respect `WidgetStyleTokens` via `read_widget_style()` if the widget needs app-supplied colors.
5. Use compact geometry (no padding larger than 10 px, no controls taller than 44 px by default).
6. Connect to `theme.theme_changed` signal to trigger repaint on theme switch.
