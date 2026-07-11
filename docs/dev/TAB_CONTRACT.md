# Tab Contract

The tab system allows adding new operation modes to the application without modifying the core codebase. Each tab is a self-contained mini-module with its own resources, translations, and state.

## File Structure

```
src/tabs/<tab_name>/
    __init__.py
    tab.py              # TabContract implementation
    controller.py       # Tab logic
    widget.py           # UI widget
    models.py           # Data models (optional)
    resources/
        i18n/
            en/<namespace>.json
            ru/<namespace>.json
        icons/          # (optional)
    tests/
        __init__.py
        contracts/      # Structural dogmas (AST-based)
        render/         # Rendering pass contracts
        runtime/        # Lifecycle and state contracts
        plugins/        # Plugin-specific contracts
        video/          # Video editor contracts (image_compare only)
        conftest.py     # Shared fixtures for this tab's tests (optional)
```

## TabContract (ABC)

```python
from tabs.contract import TabContract, TabContext

class MyTab(TabContract):
    @property
    def session_type(self) -> str:
        """Unique session type identifier, e.g., 'multi_compare'."""

    @property
    def display_name(self) -> str:
        """Name used for menus and tooltips."""

    @property
    def icon(self) -> QIcon | None:
        """Icon for the session creation menu. Returns None for no icon."""

    @property
    def resources_dir(self) -> Path | None:
        """Path to tab resources. Returns None if there are no resources."""

    @property
    def i18n_namespace(self) -> str | None:
        """Translation namespace prefix. Files are located in resources/i18n/<lang>/<namespace>.json."""

    def create_page(self, parent: QWidget, context: TabContext) -> QWidget:
        """
        Creates the root page widget.
        Called once during application startup.
        The returned widget is added to the workspace_stack.
        """

    def on_activated(self, context: TabContext) -> None:
        """Called when switching to this tab."""

    def on_deactivated(self, context: TabContext) -> None:
        """Called when switching away from this tab."""

    def accepts_drop(self, paths: list[Path]) -> bool:
        """Returns True if the tab accepts the dropped files."""

    def handle_drop(self, paths: list[Path]) -> None:
        """Processes the drop. Called only if accepts_drop returned True."""

    def on_session_created(self, session_id: str, context: TabContext) -> None:
        """Notification that a session of this type was created."""

    def on_session_closed(self, session_id: str, context: TabContext) -> None:
        """Notification that a session of this type was closed."""

    def dispose(self) -> None:
        """Cleanup performed when the tab is unloaded."""
```

## TabContext

The context is passed to all lifecycle methods. It provides access to services without requiring direct imports:

```python
class TabContext:
    store         # Global application state
    event_bus     # Event bus
    thread_pool   # Thread pool for background tasks
    main_window   # Reference to the main window
    settings      # Application settings

    def get_active_session(self) -> Any
    def tr(self, key: str, default: str | None = None) -> str
```

## TabRegistry

The registry automatically discovers all tabs at startup:

1. Scans `src/tabs/` using `pkgutil`.
2. For each sub-package, it imports `tabs.<name>.tab`.
3. Locates subclasses of `TabContract`.
4. Creates instances and registers them by `session_type`.

Packages with a `_` prefix are ignored. The `contract` and `registry` modules are skipped.

### Registry API

```python
registry = TabRegistry()
registry.discover()                           # Auto-discovery
registry.install_pages(stack, context)        # Create pages in QStackedWidget
registry.get_page(session_type) -> QWidget    # Retrieve page by type
registry.activate(session_type)               # Notify activation
registry.deactivate(session_type)             # Notify deactivation
registry.route_drop(session_type, paths)      # Route drag-and-drop
registry.dispose_all()                        # Cleanup
```

## Event Routing

- **Page Switching**: `sync_session_mode(session_type)` checks the registry. If the type is found, it displays the tab's page and calls `activate()`.
- **Drag & Drop**: `WindowEventHandler` checks the active session. If its type is registered in the registry, it calls `registry.route_drop()`.
- **Visibility Settings**: Controlled via a checkbox in Settings > Appearance. The tab bar is hidden by default.

## Translations

Each tab stores its own translations in `resources/i18n/<lang>/<namespace>.json`. Keys are accessible via `context.tr("key")` or directly through the application's translation system after the namespace is registered.

## Tests

A tab owns its own tests, just like it owns its own resources. Any test that
imports `tabs.<tab_name>.*` — directly or via a lazy import inside a test
function — belongs under `src/tabs/<tab_name>/tests/`, not under the
top-level `tests/` tree.

```
src/tabs/<tab_name>/tests/
    __init__.py
    contracts/     # AST-scan dogmas specific to this tab's canvas features/passes
    render/        # Fake-context tests for this tab's render passes and scene
    runtime/       # Lifecycle/state contracts specific to this tab
    plugins/       # Tests for this tab's plugin-facing behavior (export, settings, ...)
    video/         # image_compare only — video editor contracts
```

Rules:

- Mirror the type-based subfolders (`contracts/`, `render/`, `runtime/`,
  `plugins/`, ...) used by the top-level `tests/` tree — see
  [TESTING.md](TESTING.md) for what each subfolder is for. This keeps the
  "one file — one topic" discipline even though tests are now split by tab.
- `sys.path` resolution for `src/` still comes from pytest's own rootdir
  package-insertion (every directory down to `tests/` has an `__init__.py`),
  not from `tests/conftest.py` — that conftest only applies to the top-level
  `tests/` tree. If a moved test used a `Path(__file__).parents[N]` trick to
  find the repo root, recompute `N` for the new depth
  (`src/tabs/<tab>/tests/<kind>/test_x.py` is 5 levels below repo root).
- Tests that exercise the tab **mechanism** itself — the registry, the
  `TabContract` ABC, generic drop-routing/dispose lifecycle — stay in
  `tests/contracts/` and `tests/runtime/` even if they instantiate one
  concrete tab as an example. Only tests whose assertions are actually about
  that tab's behavior move into its `tests/` folder.
- Run a single tab's suite the same way as any other pytest path:
  `pytest src/tabs/image_compare/tests/`.

## Isolation Rule: Do Not Borrow App-Level Keys or Theme Tokens

A tab is a self-contained module. Treat the host application's resource
namespaces as **private to the host** — they can be renamed, removed, or
restructured at any major update without warning to tabs.

**Do not, under any circumstances:**

- Reference i18n keys from the main app namespace (e.g. `app.*`, `main.*`,
  `common.*`, `settings.*`, anything outside your tab's own `<namespace>`).
  Even if a string looks identical to one in the host — copy it into your
  own JSON.
- Read QSS classes, theme colors, design tokens, or icon names from
  `src/shared_toolkit/` or the host's theming layer. If you need a color
  or icon, vendor it in `resources/icons/` or define it locally.
- Import constants, enums, or labels from `src/plugins/settings/`,
  `src/ui/...`, or any host-side UI module purely to reuse a string or
  a styling value.

**Why this matters.** The host app evolves on its own schedule:
translation keys get split, theme tokens get renamed, settings namespaces
get restructured. Nothing in the build or runtime guarantees that a
borrowed key still resolves after an upgrade — and the breakage is
silent (missing label shows the key string; missing color falls back to
black/transparent). Nobody on the host side will notice that a tab quietly
broke, because the host's own tests pass.

**The rule of thumb:** if you delete `src/resources/` and `src/shared_toolkit/`
entirely, your tab must still render its UI correctly (modulo the host
chrome around it). Everything visual or textual that your tab needs lives
under `src/tabs/<your_tab>/resources/`.

This isolation is part of the tab contract and is enforced by
`tests/contracts/test_tabs.py`, `tests/contracts/test_tabs_isolation.py` and
`tests/runtime/test_tabs_lifecycle.py` (see [TESTING.md](TESTING.md) §Каталог).
These three stay in the top-level `tests/` tree because they check the
registry/contract mechanism itself, not a specific tab's behavior — see
§Tests above.

## How to Add a New Tab

1. Create a package in `src/tabs/<name>/`.
2. Implement the `TabContract` in `tab.py`.
3. Create the widget and controller.
4. Add translation files to `resources/i18n/`.
5. Add tests under `tests/` in the new tab's own `src/tabs/<name>/tests/` (see §Tests).
6. Done — the registry will pick it up automatically.

No changes are required in `main_window_ui.py`, `window_event_handler.py`, or other core files.