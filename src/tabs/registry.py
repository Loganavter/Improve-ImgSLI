"""Tab registry — auto-discovers and manages workspace tabs.

`TabRegistry` is a thin owner: construction, instance state, and
delegator methods only. The actual logic lives in `tabs/use_cases/*` as
plain functions taking the registry as their first argument, per
docs/dev/CODE_PATTERNS.md's "thin owner + use_cases/ module" pattern.
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from PySide6.QtWidgets import QStackedWidget, QWidget

from tabs.contract import TabContext, TabContract
from tabs.lazy_tab_service import LazyTabService  # noqa: F401  (re-exported: existing call sites do `from tabs.registry import LazyTabService`)
from tabs.use_cases import (
    appearance,
    capability_routing,
    discovery,
    pages,
    session_lifecycle,
    session_persistence,
)

logger = logging.getLogger("ImproveImgSLI")

TabDiscoveryTier = Literal["bootstrap", "deferred", "all"]

_shared_registry: "TabRegistry | None" = None

def get_shared_tab_registry() -> "TabRegistry":
    """Process-wide, lazily-discovered `TabRegistry` for hot-path lookups.

    Tab discovery instantiates every registered tab class, so hot paths
    (per-frame/per-mouse-move code) must not call `TabRegistry().discover()`
    fresh each time. Use this instead of constructing a new registry when
    the call site only needs `create_service`/`get_tab` and doesn't own the
    app-lifetime registry itself (e.g. `ui._tab_registry`).

    The shared registry loads bootstrap tabs only; call ``discover()`` (no
    tier) elsewhere when deferred tabs must be present.
    """
    global _shared_registry
    if _shared_registry is None:
        _shared_registry = TabRegistry()
        _shared_registry.discover(tier="bootstrap")
    return _shared_registry

class TabRegistry:
    """
    Discovers tab implementations from the `tabs/` package and manages
    their lifecycle within the workspace.

    Singleton by construction (see ``__new__``): every ``TabRegistry()``
    call anywhere in the app returns the same instance. This is load-bearing
    for ``create_service``/``create_main_window_feature`` — they resolve
    strictly against ``self._tabs[self._active_session_type]`` (no fallback
    to any other tab), so ``_active_session_type`` must be the one true,
    process-wide value that ``activate()``/``deactivate()`` maintain. Before
    this was a singleton, every ad-hoc ``TabRegistry(); .discover()`` call
    site got its own blank instance whose ``_active_session_type`` was
    always ``None`` — which is exactly what made the old "first tab that
    answers wins" fallback behavior possible (and buggy) in the first place.
    See docs/dev/tabs/capability-mechanisms.md.
    """

    _instance: "TabRegistry | None" = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._tabs: dict[str, TabContract] = {}
        self._pages: dict[str, QWidget] = {}
        self._pending_pages: dict[str, TabContract] = {}
        self._context: TabContext | None = None
        self._active_session_type: str | None = None
        self._active_session_id: str | None = None
        self._discovered_tiers: set[str] = set()
        self._appearance_stale: set[str] = set()

    @property
    def registered_types(self) -> list[str]:
        return list(self._tabs.keys())

    @property
    def deferred_loaded(self) -> bool:
        return "deferred" in self._discovered_tiers or "all" in self._discovered_tiers

    # -- discovery (tabs/use_cases/discovery.py) --------------------------

    def discover(self, *, tier: TabDiscoveryTier | None = None) -> None:
        discovery.discover(self, tier=tier)

    def get_tab(self, session_type: str) -> TabContract | None:
        return self._tabs.get(session_type)

    def get_active_tab(self) -> TabContract | None:
        """Return the `TabContract` instance for the currently active session.

        For host-generic code (event routing, window chrome) that needs to
        call a behavioral `TabContract` method directly (`owns_widget`,
        `clear_transient_text_focus`, ...) rather than construct a service.
        `None` if no session is active yet (startup, session switching) —
        callers already handle `None` (e.g. image-label mouse routing falls
        back to raw event positions).
        """
        return self._tabs.get(self._active_session_type)

    def list_tabs(self) -> list[TabContract]:
        return list(self._tabs.values())

    # -- capability routing (tabs/use_cases/capability_routing.py) --------

    def contribute_all_settings(self) -> None:
        capability_routing.contribute_all_settings(self)

    def contribute_all_help(self) -> None:
        capability_routing.contribute_all_help(self)

    def contribute_settings_for(self, session_type: str) -> None:
        capability_routing.contribute_settings_for(self, session_type)

    def create_main_window_feature(self, feature_id: str, **kwargs: Any) -> Any:
        return capability_routing.create_main_window_feature(self, feature_id, **kwargs)

    def create_service(self, service_id: str, *args: Any, **kwargs: Any) -> Any:
        return capability_routing.create_service(self, service_id, *args, **kwargs)

    def create_service_for(
        self, session_type: str, service_id: str, *args: Any, **kwargs: Any
    ) -> Any:
        return capability_routing.create_service_for(
            self, session_type, service_id, *args, **kwargs
        )

    def create_startup_service(self, service_id: str, *args: Any, **kwargs: Any) -> Any:
        return capability_routing.create_startup_service(self, service_id, *args, **kwargs)

    def notify_all(self, hook_id: str, *args: Any, **kwargs: Any) -> None:
        capability_routing.notify_all(self, hook_id, *args, **kwargs)

    def _first_tab_answering(
        self, method_name: str, *args: Any, **kwargs: Any
    ) -> "TabContract | None":
        return capability_routing._first_tab_answering(self, method_name, *args, **kwargs)

    def _first_tab_answering_result(
        self, method_name: str, *args: Any, **kwargs: Any
    ) -> tuple["TabContract", object] | None:
        return capability_routing._first_tab_answering_result(
            self, method_name, *args, **kwargs
        )

    # -- page lifecycle (tabs/use_cases/pages.py) --------------------------

    def assemble_host_pages(self, ui: Any) -> None:
        pages.assemble_host_pages(self, ui)

    def finalize_host_pages(self, ui: Any) -> None:
        pages.finalize_host_pages(self, ui)

    def apply_host_session_mode(
        self,
        session_type: str,
        ui: Any,
        session_title: str | None = None,
    ) -> bool:
        return pages.apply_host_session_mode(self, session_type, ui, session_title=session_title)

    def install_pages(self, stack: QStackedWidget, context: TabContext) -> None:
        pages.install_pages(self, stack, context)

    def _ensure_page(self, session_type: str) -> QWidget | None:
        return pages._ensure_page(self, session_type)

    def _create_and_assemble_page(
        self, session_type: str, tab: TabContract
    ) -> QWidget | None:
        return pages._create_and_assemble_page(self, session_type, tab)

    def install_missing_pages(self, stack: QStackedWidget) -> tuple[str, ...]:
        return pages.install_missing_pages(self, stack)

    def get_page(self, session_type: str) -> QWidget | None:
        return pages.get_page(self, session_type)

    # -- session activation lifecycle (tabs/use_cases/session_lifecycle.py)

    def bootstrap_default_tab(self) -> "TabContract | None":
        return session_lifecycle.bootstrap_default_tab(self)

    def _bootstrap_default_tab(self) -> "TabContract | None":
        return session_lifecycle._bootstrap_default_tab(self)

    def activate_default(self) -> None:
        session_lifecycle.activate_default(self)

    def activate(self, session_type: str) -> None:
        session_lifecycle.activate(self, session_type)

    def _sync_active_session_for_type(self, session_type: str) -> None:
        session_lifecycle._sync_active_session_for_type(self, session_type)

    def _resolve_active_session_id(self, session_type: str) -> str | None:
        return session_lifecycle._resolve_active_session_id(self, session_type)

    def notify_active_session_changed(
        self,
        session_id: str,
        session_type: str,
        previous_session_id: str | None = None,
    ) -> None:
        session_lifecycle.notify_active_session_changed(
            self, session_id, session_type, previous_session_id
        )

    def deactivate(self, session_type: str) -> None:
        session_lifecycle.deactivate(self, session_type)

    # -- session persistence (tabs/use_cases/session_persistence.py) ------

    def notify_session_created(self, session_type: str, session_id: str) -> None:
        session_persistence.notify_session_created(self, session_type, session_id)

    def serialize_session(self, session_type: str, session_id: str) -> dict[str, Any] | None:
        return session_persistence.serialize_session(self, session_type, session_id)

    def collect_pixel_cache_sources(
        self, session_type: str, session_id: str
    ) -> dict[str, Any]:
        return session_persistence.collect_pixel_cache_sources(self, session_type, session_id)

    def deserialize_session(
        self, session_type: str, session_id: str, data: dict[str, Any]
    ) -> None:
        session_persistence.deserialize_session(self, session_type, session_id, data)

    def rehydrate_session(self, session_type: str, session_id: str) -> None:
        session_persistence.rehydrate_session(self, session_type, session_id)

    def duplicate_session(
        self, session_type: str, source_session_id: str
    ) -> dict[str, Any] | None:
        return session_persistence.duplicate_session(self, session_type, source_session_id)

    def notify_session_closed(self, session_type: str, session_id: str) -> None:
        session_persistence.notify_session_closed(self, session_type, session_id)

    # -- misc ---------------------------------------------------------------

    def route_drop(
        self,
        session_type: str,
        paths: list,
        hint: dict | None = None,
    ) -> bool:
        """Route a file drop to the active tab. Returns True if handled."""
        tab = self._tabs.get(session_type)
        if tab is None:
            logger.debug("TabRegistry.route_drop: no tab for %s", session_type)
            return False
        from pathlib import Path as P
        resolved = [P(p) if not isinstance(p, P) else p for p in paths]
        accepts = tab.accepts_drop(resolved)
        if accepts:
            handled = tab.handle_drop(resolved, hint=hint)
            return bool(True if handled is None else handled)
        return False

    def apply_appearance(self, host_window) -> None:
        appearance.apply_appearance(self, host_window)

    def flush_stale_appearance(self, host_window) -> None:
        appearance.flush_stale_appearance(self, host_window)

    def notify_window_shutdown(self, host_window) -> None:
        for tab in self._tabs.values():
            try:
                tab.on_window_shutdown(host_window)
            except Exception as e:
                logger.error(f"Tab shutdown hook error ({tab.session_type}): {e}")

    def dispose_all(self) -> None:
        for tab in self._tabs.values():
            try:
                tab.dispose()
            except Exception:
                pass
        self._tabs.clear()
        self._pages.clear()
        self._pending_pages.clear()
        self._appearance_stale.clear()
        self._active_session_type = None
