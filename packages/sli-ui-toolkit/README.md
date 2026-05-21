# SLI UI Toolkit

`sli-ui-toolkit` is a reusable PyQt6 widget and UI-support library.

Use it when you want:

- custom-painted compact controls;
- a unified button system;
- theme-aware widgets and flyouts;
- app-injected icons, translations, and overlay behavior.

## Start Here

This file is the integration entry point, not the full reference.

- Full public API: [docs/API_CATALOG.md](/home/jorj/Загрузки/Improve-ImgSLI/packages/sli-ui-toolkit/docs/API_CATALOG.md)
- Internal structure: [docs/ARCHITECTURE.md](/home/jorj/Загрузки/Improve-ImgSLI/packages/sli-ui-toolkit/docs/ARCHITECTURE.md)
- Visual conventions: [docs/DESIGN_LANGUAGE.md](/home/jorj/Загрузки/Improve-ImgSLI/packages/sli-ui-toolkit/docs/DESIGN_LANGUAGE.md)
- Docs index: [docs/README.md](/home/jorj/Загрузки/Improve-ImgSLI/packages/sli-ui-toolkit/docs/README.md)

## Import Layers

Use these import layers on purpose:

- `sli_ui_toolkit`
  Small top-level bootstrap surface.
- `sli_ui_toolkit.widgets`
  Main public widget catalog.
- `sli_ui_toolkit.i18n`
  Translation manager and helpers.
- `sli_ui_toolkit.icons`
  Icon resolver configuration.
- `sli_ui_toolkit.theme`
  Theme manager.
- `sli_ui_toolkit.managers`
  Flyout and timer helpers.
- `sli_ui_toolkit.services`
  Utility services such as prewarm helpers.

If you are building app UI, most of the time you want `sli_ui_toolkit.widgets`.

## Configuration Hooks

App-specific behavior is injected at startup:

- `configure_icon_resolver(...)`
- `configure_toolkit(...)`
- `configure_i18n(...)`

These hooks keep the toolkit reusable while letting the host app supply:

- icon lookup;
- translation roots;
- overlay-layer resolution;
- timing constants.

## Quick Start

```python
from pathlib import Path

from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout

from sli_ui_toolkit import FlyoutTimingConfig, configure_i18n, configure_toolkit
from sli_ui_toolkit.icons import configure_icon_resolver
from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.widgets import Button, ComboBox, install_application_tooltips

app = QApplication([])

theme = ThemeManager.get_instance()
theme.register_palettes(light_palette={...}, dark_palette={...})
theme.register_qss_path(str(Path("resources/qss/app.qss")))
theme.set_theme("dark", app)

configure_icon_resolver(resolver=my_icon_lookup)

configure_toolkit(
    timings=FlyoutTimingConfig(
        transient_auto_hide_delay_ms=300,
        flyout_animation_duration_ms=150,
        text_settings_flyout_animation_duration_ms=150,
    ),
    overlay_resolver=lambda widget: getattr(widget.window(), "overlay_layer", None),
)

configure_i18n(i18n_root=Path("resources/i18n"))
install_application_tooltips(app)

window = QWidget()
layout = QVBoxLayout(window)

save_button = Button("save", text="Save", variant="accent")
mode_combo = ComboBox()
mode_combo.addItems(["Fast", "Balanced", "Quality"])

layout.addWidget(save_button)
layout.addWidget(mode_combo)
window.show()

app.exec()
```

## First Widgets To Reach For

- `Button`
  Unified icon/text/toggle/menu/scrollable button system.
- `ComboBox`
  Custom-painted combo box with popup, search, and keyboard navigation.
- `CustomLineEdit`
  Themed editable text field.
- `SidebarDialogShell`
  Settings/help style dialog shell.
- `ScrollableDialogPage`
  Scrollable dialog page container.
- `DialogActionBar`
  Standard primary/secondary action row.
- `MarkdownHelpDialog`
  Reusable markdown help/documentation dialog.

Usage details live in [docs/API_CATALOG.md](/home/jorj/Загрузки/Improve-ImgSLI/packages/sli-ui-toolkit/docs/API_CATALOG.md).

## Notes

- `ComboBox` is a custom widget, not a full `QComboBox` drop-in replacement.
- The toolkit is designed around custom-painted controls, not QSS-skinned stock widgets.
- App-specific icons and translations should stay outside the toolkit and be injected through configuration.
