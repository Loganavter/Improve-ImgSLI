# Tab package structure

## File layout

The minimum every tab has, plus the optional subsystems actually used today.
`controller.py` is **not** universal (`image_compare` keeps its logic in
`_session_controller.py` + `service_factory.py` + `use_cases/`,
`session_picker` has none).

```
src/tabs/<tab_name>/
    __init__.py
    tab.py                  # TabContract implementation (required)
    plugin.py               # @plugin(...) + ISessionPlugin — required to be creatable
                            # from the New Session picker (see overview.md)
    widget.py               # UI widget
    bootstrap_reducers.py   # Registers the tab's reducers (IC / MC / gallery)
    actions.py              # Action catalog + keymap defaults (gallery / MC)
    models.py               # Tab-level data models (not the Redux slice)
    controller.py           # Tab logic — MC, gallery (optional)
    help.py                 # contribute_help(...) — tab-owned Help topics
    debug.py                # Debug toggles for this tab (optional)
    icons.py                # Icon enum + get_icon()
    services/               # Pure services (no Qt widgets) — ranking, export, IO, ...
    use_cases/              # Plain functions over the tab's owner object
    state/                  # Redux slice: actions.py, models.py, reducer.py, selectors.py
    analysis/               # gallery only: engine context builder, runner, producers, read
    pipeline/               # canvas render pipeline (IC / MC)
    canvas/                 # canvas widget + features/ packages (IC / MC)
    presenters/             # presenters over the widget (IC)
    ui/                     # sub-widgets, flyouts, dialogs, chrome
    events/                 # tab-owned event handlers
    plugins/                # nested tab plugins (IC: plugins/video_editor/)
    resources/
        i18n/{en,ru,pt_BR,zh}/<namespace>.json   # IC/MC also ship tooltips.json here
        help/{en,ru,pt_BR,zh}/*.md
        icons/{light,dark}/*.svg
    docs/                   # tab-owned living docs + investigations
    tests/
        __init__.py
        contracts/      # Structural dogmas (AST-based)
        render/         # Rendering pass contracts
        runtime/        # Lifecycle and state contracts
        plugins/        # Plugin-specific contracts
        video/          # Video editor contracts (image_compare only)
        compare_unify/  # Comparison-unification contracts (IC / MC)
        conftest.py     # Shared fixtures for this tab's tests
```

Per-tab reality check (the folder set is **per tab**, not a mandate):

| Tab | Logic home | Extra top-level dirs |
|---|---|---|
| `image_compare` | `_session_controller.py`, `service_factory.py`, `use_cases/`, `presenters/` | `canvas/`, `pipeline/`, `state/`, `events/`, `plugins/video_editor/`, `actions/` |
| `multi_compare` | `controller.py`, `use_cases/`, `scene/` | `canvas/`, `pipeline/`, `state/`, `shaders/`, `actions.py` |
| `image_gallery` | `controller.py`, `use_cases/` | `analysis/`, `state/`, `actions.py`, huge flat `tests/` |
| `session_picker` | `tab.py` + `widget.py` | `recent/`, `prelayout.py`, `geometry.py` |

Shared helpers (not tab packages): `src/tabs/icon_loader.py`
(`tab_icon_resolver()`), `src/tabs/lazy_tab_service.py`,
`src/tabs/host_helpers.py`, `src/tabs/save_toast.py`, `src/tabs/conftest.py`, and
the intra-tab `src/tabs/_shared/` (see [isolation.md](isolation.md)).

## Translations

Each tab stores its own translations in `resources/i18n/<lang>/<namespace>.json`;
discovery registers the directory during `TabRegistry.discover()` (plus any
`extra_i18n_roots()`). Tab code translates through `context._tr("key")` or
`context._tr_lang("key", language)` — **there is no `context.tr`**. Keys must
stay in the tab's own namespace (see [isolation.md](isolation.md)).

`image_compare` and `multi_compare` ship two namespaces in the same directory
(`image_compare.json` + `tooltips.json`), so a single tab can hold more than one
JSON file per language. A tab with a nested subpackage that owns its own i18n
(the video editor) lists that directory from `extra_i18n_roots()` — otherwise
those keys are never registered:

```python
def extra_i18n_roots(self) -> list[Path]:
    return [Path(__file__).parent / "plugins" / "video_editor" / "resources" / "i18n"]
```

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
