# Tab package structure

## File layout

```
src/tabs/<tab_name>/
    __init__.py
    tab.py              # TabContract implementation
    controller.py       # Tab logic
    widget.py           # UI widget
    models.py           # Data models (optional)
    icons.py            # Icon enum + get_icon() (standard when tab has UI icons)
    help.py             # contribute_help(...) — tab-owned Help topics (optional)
    resources/
        i18n/
            en/<namespace>.json
            ru/<namespace>.json
        help/           # tab-owned Help bodies (<lang>/*.md)
            en/
            ru/
        icons/          # tab-owned SVG assets
            light/*.svg
            dark/*.svg
    tests/
        __init__.py
        contracts/      # Structural dogmas (AST-based)
        render/         # Rendering pass contracts
        runtime/        # Lifecycle and state contracts
        plugins/        # Plugin-specific contracts
        video/          # Video editor contracts (image_compare only)
        conftest.py     # Shared fixtures for this tab's tests (optional)
```

Shared helper (not a tab package): `src/tabs/icon_loader.py` — `tab_icon_resolver()`.

## Translations

Each tab stores its own translations in `resources/i18n/<lang>/<namespace>.json`.
Keys are accessible via `context.tr("key")` or through the application's
translation system after the namespace is registered during `TabRegistry.discover()`.

See [RESOURCES_I18N.md](../RESOURCES_I18N.md) for the global i18n pipeline.

## Tab-owned icons

Tabs vendor their own SVG assets under `resources/icons/{light,dark}/` and
expose them through `icons.py`:

```python
# tabs/<tab>/icons.py
from enum import Enum
from pathlib import Path
from tabs.icon_loader import tab_icon_resolver

_TAB_DIR = Path(__file__).resolve().parent
get_icon = tab_icon_resolver(_TAB_DIR)

class Icon(Enum):
    PHOTO = "photo_icon.svg"
```

Tab UI code imports `Icon` / `get_icon` from its own package — **never**
`ui.icon_manager.AppIcon`. Toolkit widgets (`Button(Icon.X)`) still resolve
correctly: `get_app_icon()` delegates enums whose module is `tabs.*.icons` to
that tab's `get_icon()`.

For icons shown outside the tab (session picker cards), implement
`TabContract.icon` and let consumers call `context.call_service("get_tab_icon",
session_type)`.

Adding a new icon: copy both theme SVGs, add an `Icon` enum member, use it in
tab code. Enforced by `tests/contracts/test_tab_icons.py`.

See [RESOURCES_I18N.md §Icons](../RESOURCES_I18N.md#icons) for the full app vs tab icon split.
