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

## How to Add a New Tab

1. Create a package in `src/tabs/<name>/`.
2. Implement the `TabContract` in `tab.py`.
3. Create the widget and controller.
4. Add translation files to `resources/i18n/`.
5. Done — the registry will pick it up automatically.

No changes are required in `main_window_ui.py`, `window_event_handler.py`, or other core files.