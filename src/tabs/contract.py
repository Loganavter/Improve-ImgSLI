"""Tab contract — interface that every workspace tab must implement."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QWidget

class TabContract(ABC):
    """
    Base class for workspace tabs.

    Each tab is a self-contained mini-app that owns:
    - its own widget tree (page)
    - its own resources (icons, stylesheets)
    - its own translations (i18n keys under its namespace)
    - its own controller/state

    The host shell provides:
    - a slot in QStackedWidget
    - session lifecycle signals
    - drop routing
    """

    @property
    @abstractmethod
    def session_type(self) -> str:
        """Unique session type identifier, e.g. 'multi_compare'."""

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable tab name for menus and tooltips."""

    def localized_display_name(self, language: str) -> str:
        """Localized tab name. Default falls back to ``display_name``.

        Override to look up a translation key — tabs that own their i18n
        should not require host-side hardcoded mappings.
        """
        return self.display_name

    @property
    def icon(self) -> QIcon | None:
        """Optional icon for the new-session menu."""
        return None

    @property
    def resources_dir(self) -> Path | None:
        """Path to tab-owned resources (icons, qss, etc). None if no resources."""
        return None

    @property
    def i18n_namespace(self) -> str | None:
        """
        Translation namespace prefix, e.g. 'multi_compare'.
        Tab translations live at <app_i18n_root>/<lang>/tabs/<namespace>.json
        or are embedded alongside the tab package.
        """
        return None

    @abstractmethod
    def create_page(self, parent: QWidget, context: TabContext) -> QWidget:
        """
        Create and return the root widget for this tab's page.
        Called once during app startup. The returned widget is added to workspace_stack.
        """

    def on_activated(self, context: TabContext) -> None:
        """Called when this tab's session becomes the active workspace session."""

    def on_deactivated(self, context: TabContext) -> None:
        """Called when switching away from this tab's session."""

    def accepts_drop(self, paths: list[Path]) -> bool:
        """Return True if this tab can handle the given file drop."""
        return False

    def handle_drop(self, paths: list[Path]) -> None:
        """Process dropped files. Only called if accepts_drop returned True."""

    def on_session_created(self, session_id: str, context: TabContext) -> None:
        """Called when a new session of this tab's type is created."""

    def on_session_closed(self, session_id: str, context: TabContext) -> None:
        """Called when a session of this tab's type is closed."""

    def on_quick_save(self, context: TabContext) -> None:
        """Handle the cross-tab quick-save button when this tab is active."""

    def contribute_settings(self, registry: "SettingsRegistry") -> None:
        """Register settings sections this tab contributes.

        Called once during app startup. ``registry`` provides ``add(section_id,
        title, factory, *, tab=None)`` where ``tab`` is the session_type the
        section belongs to (None = always shown).
        """

    def dispose(self) -> None:
        """Cleanup when the tab is being unloaded."""

class TabContext:
    """
    Context object passed to tabs — provides access to app services
    without importing app internals.
    """

    def __init__(
        self,
        store: Any = None,
        event_bus: Any = None,
        thread_pool: Any = None,
        main_window: Any = None,
        settings: Any = None,
        services: dict[str, Any] | None = None,
    ):
        self.store = store
        self.event_bus = event_bus
        self.thread_pool = thread_pool
        self.main_window = main_window
        self.settings = settings
        self.services = dict(services or {})

    def get_active_session(self) -> Any:
        if self.store:
            return self.store.get_active_workspace_session()
        return None

    def tr(self, key: str, default: str | None = None) -> str:
        """Translate a key using the app's i18n system."""
        try:
            from resources.translations import tr

            settings = self.settings or getattr(self.store, "settings", None)
            language = getattr(settings, "current_language", "en")
            result = tr(key, language)
            return result if result != key else (default or key)
        except Exception:
            return default or key

    def call_service(self, service_id: str, *args, **kwargs) -> Any:
        """Call a host capability without importing host implementation details."""
        service = self.services.get(service_id)
        if not callable(service):
            raise RuntimeError(f"Tab host service is unavailable: {service_id}")
        return service(*args, **kwargs)
