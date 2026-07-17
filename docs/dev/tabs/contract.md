# TabContract & TabContext

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

    @property
    def is_bootstrap_default(self) -> bool:
        """True for exactly one tab — see capability-mechanisms.md §Bootstrap seam. Default False."""

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

    def on_active_session_changed(self, session_id: str, context: TabContext) -> None:
        """Called when the active *session id* changes while this tab type
        stays visible (e.g. IC→IC or MC→MC). Use for per-session snapshot/
        restore; ``on_activated`` is for tab-type visibility only."""

    def serialize_session(self, session_id: str, context: TabContext) -> dict | None:
        """JSON-serializable project snapshot, or ``None`` if unsupported."""

    def deserialize_session(
        self, session_id: str, data: dict, context: TabContext
    ) -> None:
        """Restore persisted metadata into an already-created session."""

    def rehydrate_session(self, session_id: str, context: TabContext) -> None:
        """Reload runtime media (decoded pixels) from paths after
        ``deserialize_session``."""

    def duplicate_session(
        self, source_session_id: str, context: TabContext
    ) -> dict | None:
        """Return a snapshot suitable for cloning ``source_session_id``."""

    def dispose(self) -> None:
        """Cleanup performed when the tab is unloaded."""

    def create_service(self, service_id: str, *args, **kwargs) -> Any:
        """See capability-mechanisms.md. Base implementation returns None."""

    def create_main_window_feature(self, feature_id: str, **kwargs) -> Any:
        """Single-ID main-window feature hook — see capability-mechanisms.md."""

    def get_canvas_geometry_provider(self) -> CanvasGeometryProvider | None:
        """See capability-mechanisms.md §CanvasGeometryProvider. Base returns None."""
```

`TabContract` intentionally stays small and stable: lifecycle hooks plus the
two capability-mechanism hooks above. **Nothing else gets added here.** A new
host↔tab wiring need goes through one of the mechanisms in
[capability-mechanisms.md](capability-mechanisms.md), never through an 11th
single-purpose abstract method.

## TabContext

The context is passed to all lifecycle methods. It provides access to services
without requiring direct imports:

```python
class TabContext:
    store         # Global application state
    event_bus     # Event bus
    thread_pool   # Thread pool for background tasks
    main_window   # Reference to the main window
    settings      # Application settings
    services      # dict — see capability-mechanisms.md §TabContext.services

    def get_active_session(self) -> Any
    def tr(self, key: str, default: str | None = None) -> str
    def call_service(self, service_id: str, *args, **kwargs) -> Any
```
