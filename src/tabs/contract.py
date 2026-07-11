"""Tab contract — interface that every workspace tab must implement."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QWidget


@dataclass(frozen=True)
class TabTransitionHint:
    """How the workspace shell should mask intermediate paint glitches when
    activating this tab.

    The shell guarantees the mask stays visible for at least ``min_duration_ms``
    after the swap starts, and is hidden no later than ``max_duration_ms`` even
    if the tab never reports readiness. Tabs that want to drop the mask earlier
    can call the ``workspace.transition_mask`` service's ``release()`` once
    their first valid frame is painted.
    """

    cover_on_enter: bool = True
    min_duration_ms: int = 50
    max_duration_ms: int = 300


_DEFAULT_TRANSITION_HINT = TabTransitionHint()


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

    def transition_hint(self) -> TabTransitionHint:
        """How the shell should cover paint glitches when entering this tab.

        Override in tabs with complex first-paint layouts to extend the mask
        window (or disable it). The default keeps a ~50 ms mask, capped at
        300 ms in case the tab never signals readiness.
        """
        return _DEFAULT_TRANSITION_HINT

    def on_activated(self, context: TabContext) -> None:
        """Called when this tab's session becomes the active workspace session."""

    def on_deactivated(self, context: TabContext) -> None:
        """Called when switching away from this tab's session."""

    def accepts_drop(self, paths: list[Path]) -> bool:
        """Return True if this tab can handle the given file drop."""
        return False

    def handle_drop(
        self, paths: list[Path], hint: dict | None = None
    ) -> None:
        """Process dropped files. Only called if accepts_drop returned True.

        ``hint`` carries host-side context (e.g. ``{"is_left_area": bool}``
        from mouse position) so the tab can route the drop without the host
        embedding tab-specific concepts.
        """

    def apply_appearance(self, host_window) -> None:
        """Repaint tab-owned widgets when the theme changes."""

    def on_window_shutdown(self, host_window) -> None:
        """Tear down tab-owned timers / threads when the host window closes."""

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

    def create_main_window_feature(self, feature_id: str, **kwargs: Any) -> Any:
        """Create a tab-owned feature still hosted by the legacy main presenter.

        This is a transition hook for code that has not yet moved fully into
        the tab page. The host may request a named feature through the tab
        registry, but must not import tab internals directly.
        """
        return None

    def create_service(self, service_id: str, *args: Any, **kwargs: Any) -> Any:
        """Create a tab-owned service requested through the tab registry."""
        return None

    def assemble_host_page(self, ui: Any) -> bool:
        """Assemble legacy host-owned primitives into this tab's page.

        Transitional hook: tabs that still receive primitive widgets from the
        host can finish page assembly without the host importing or naming the
        tab directly.
        """
        return False

    def apply_host_session_mode(self, ui: Any, session_title: str | None = None) -> bool:
        """Apply host chrome state for this tab when it becomes active."""
        return False

    def register_canvas_features(self) -> None:
        """Register tab-owned canvas feature packages with the host canvas shell.

        The host owns generic canvas contracts and registries, but must not
        import tab internals. Tabs that provide canvas features register their
        package here during tab discovery.
        """

    def extra_i18n_roots(self) -> list[Path]:
        """Directories with translation JSON beyond `resources_dir`'s i18n.

        `TabRegistry.discover` auto-registers `<tab>/resources/i18n`, but a
        tab with nested subpackages (each owning their own i18n folder) can't
        reach the host's i18n registration itself without importing
        `resources.translations` — forbidden by the tab isolation contract.
        Override to list those extra directories; the registry registers
        each one that exists.
        """
        return []

    def create_default_session_data(self) -> Any:
        """Return a fresh `core.store_viewport.SessionData` for a new session
        of this tab's type, or `None` to use the generic default.

        Called once per `create_workspace_session()` via a factory registered
        during tab discovery (see `TabRegistry.discover`). Override when a tab
        needs its own session-scoped state shape instead of the comparison-tab
        default (`ImageSessionState`/`RenderCacheState`) that `core` falls
        back to.
        """
        return None

    def serialize_session(self, session_id: str, context: TabContext) -> dict[str, Any] | None:
        """Return a JSON-serializable snapshot of this session for project
        save, or `None` if this tab does not support project persistence.

        Include only state that is cheap/safe to persist — source paths,
        layout, per-session settings. Do NOT include runtime-only state
        (decoded pixel buffers, GPU handles, thread pools, derived caches);
        those must be regenerated from the persisted paths/settings on load.
        """
        return None

    def deserialize_session(
        self, session_id: str, data: dict[str, Any], context: TabContext
    ) -> None:
        """Restore session-scoped state from a snapshot produced by
        `serialize_session`, into the session identified by `session_id`.

        Called after the session has been created (so its `state_slots`
        already hold blueprint defaults) — implementations should overwrite
        those defaults with `data`, not assume slots are empty.
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
