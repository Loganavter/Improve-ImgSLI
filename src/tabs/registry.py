"""Tab registry — auto-discovers and manages workspace tabs."""

from __future__ import annotations

import importlib
import logging
import pkgutil
from pathlib import Path
from typing import Any, Literal

from PySide6.QtWidgets import QStackedWidget, QWidget

from core.plugin_system.discovery_scan import tab_packages_for_tier
from tabs.contract import TabContext, TabContract
from resources.translations import add_i18n_root

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

    def discover(self, *, tier: TabDiscoveryTier | None = None) -> None:
        """Discover tab implementations from the ``tabs/`` package.

        Idempotent per tier. ``tier=None`` ensures bootstrap then deferred
        tabs (preserves defensive ``discover()`` at ~25 call sites).
        """
        if tier is None:
            self.discover(tier="bootstrap")
            self.discover(tier="deferred")
            return

        from core.startup_trace import startup_mark

        if tier in self._discovered_tiers:
            return

        if tier == "all":
            self._discover_all_modules()
        else:
            modules = tab_packages_for_tier(tier)
            for module_name in modules:
                self._discover_tab_module(module_name)

        self._discovered_tiers.add(tier)
        startup_mark(f"tab.discover.{tier}")

    def _discover_all_modules(self) -> None:
        try:
            import tabs as tabs_pkg
        except ImportError:
            return

        tabs_path = Path(tabs_pkg.__path__[0])

        for finder, module_name, is_pkg in pkgutil.iter_modules(tabs_pkg.__path__):
            if module_name.startswith("_") or module_name in ("contract", "registry"):
                continue
            self._discover_tab_module(module_name, tabs_path=tabs_path)

    def _discover_tab_module(
        self, module_name: str, *, tabs_path: Path | None = None
    ) -> None:
        if tabs_path is None:
            try:
                import tabs as tabs_pkg
            except ImportError:
                return
            tabs_path = Path(tabs_pkg.__path__[0])

        tab_i18n = tabs_path / module_name / "resources" / "i18n"
        if tab_i18n.is_dir():
            add_i18n_root(tab_i18n)

        try:
            mod = importlib.import_module(f"tabs.{module_name}.tab")
            for attr_name in dir(mod):
                obj = getattr(mod, attr_name)
                if (
                    isinstance(obj, type)
                    and issubclass(obj, TabContract)
                    and obj is not TabContract
                ):
                    instance = obj()
                    if instance.session_type in self._tabs:
                        continue
                    try:
                        instance.register_canvas_features()
                    except Exception as e:
                        logger.error(
                            "Canvas feature registration failed for tab %s: %s",
                            instance.session_type,
                            e,
                        )
                    try:
                        for extra_root in instance.extra_i18n_roots():
                            if extra_root.is_dir():
                                add_i18n_root(extra_root)
                    except Exception as e:
                        logger.error(
                            "Extra i18n root registration failed for tab %s: %s",
                            instance.session_type,
                            e,
                        )
                    try:
                        from core.store_viewport import register_session_data_factory

                        register_session_data_factory(
                            instance.session_type, instance.create_default_session_data
                        )
                    except Exception as e:
                        logger.error(
                            "Session-data factory registration failed for tab %s: %s",
                            instance.session_type,
                            e,
                        )
                    self._tabs[instance.session_type] = instance
        except (ImportError, AttributeError):
            logger.exception(
                "TabRegistry: failed to import/register tabs.%s.tab",
                module_name,
            )

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

    def contribute_all_settings(self) -> None:
        """Let every registered tab publish settings sections (broadcast)."""
        from plugins.settings.registry import get_settings_registry

        self.notify_all("contribute_settings", get_settings_registry())

    def contribute_all_help(self) -> None:
        """Collect tab Help subtrees and install them into the host tree."""
        from plugins.help.contribution import HelpContributionRegistry
        from plugins.help.tree import install_help_contributions

        registry = HelpContributionRegistry()
        self.notify_all("contribute_help", registry)
        install_help_contributions(registry)

    def contribute_settings_for(self, session_type: str) -> None:
        """Publish settings for one tab (e.g. after late discovery)."""
        tab = self._tabs.get(session_type)
        if tab is None:
            return
        from plugins.settings.registry import get_settings_registry

        try:
            tab.create_service("contribute_settings", get_settings_registry())
        except Exception as e:
            logger.error(f"contribute_settings failed for {session_type}: {e}")

    def create_main_window_feature(self, feature_id: str, **kwargs: Any) -> Any:
        """Create a legacy main-window-shell feature from the tab that provides it.

        Unlike ``create_service``, this is *not* routed by the currently
        active session. Its one caller (``ui/main_window/composer.py``)
        requests it exactly once, synchronously during app startup, before
        the user can have switched tabs — and by that point in the startup
        sequence ``_active_session_type`` already reflects the app's real
        initial workspace session (whatever `core.store.INITIAL_WORKSPACE_SESSION_TYPE`
        is — e.g. ``session_picker``), not the tab that hosts this legacy
        feature. Routing this by active session would make the app's
        startup order (session activation happening before or after
        ``compose()``) silently decide which tab answers here.

        Instead it routes **by capability**: each registered tab is asked in
        registration order (bootstrap before deferred) and the first one
        whose ``create_main_window_feature`` returns a non-``None`` answer
        provides the feature. No tab has a privileged role; whichever tab
        actually implements the feature answers. See
        docs/dev/tabs/capability-mechanisms.md.
        """
        answered = self._first_tab_answering_result(
            "create_main_window_feature", feature_id, **kwargs
        )
        if answered is None:
            return None
        # Same as create_startup_service: the probe already built the feature,
        # never call create_main_window_feature a second time.
        _tab, result = answered
        return result

    def create_service(self, service_id: str, *args: Any, **kwargs: Any) -> Any:
        """Create a service owned by the active tab.

        Resolves strictly against the tab matching ``self._active_session_type``
        — never any other registered tab. Returns ``None`` (not another
        tab's answer) if the active tab doesn't implement ``service_id``.
        See docs/dev/tabs/capability-mechanisms.md.
        """
        active = self._active_session_type
        if active is None:
            return None
        tab = self._tabs.get(active)
        if tab is None:
            return None
        try:
            return tab.create_service(service_id, *args, **kwargs)
        except Exception:
            logger.exception(
                "Tab service hook failed for %s on %s",
                service_id,
                tab.session_type,
            )
            raise

    def create_service_for(
        self, session_type: str, service_id: str, *args: Any, **kwargs: Any
    ) -> Any:
        """Create a service owned by a specific tab (not necessarily active).

        For host chrome that addresses a known hub tab by ``session_type``
        (typically ``core.store.INITIAL_WORKSPACE_SESSION_TYPE``). Prefer
        ``create_service`` when the capability belongs to the *active*
        session. Returns ``None`` if that tab is missing or does not
        implement ``service_id``. See docs/dev/tabs/capability-mechanisms.md.
        """
        tab = self._tabs.get(session_type)
        if tab is None:
            return None
        try:
            return tab.create_service(service_id, *args, **kwargs)
        except Exception:
            logger.exception(
                "Tab service-for hook failed for %s on %s",
                service_id,
                tab.session_type,
            )
            raise

    def create_startup_service(self, service_id: str, *args: Any, **kwargs: Any) -> Any:
        """Create a startup-shell service from the bootstrap-default tab.

        Resolves strictly against the tab that declares
        ``is_bootstrap_default = True`` (session_picker).  Other tabs are
        never probed — they may not have been discovered yet, and their
        pages certainly don't exist at startup.

        For capabilities needed after startup, use ``create_service``
        (active-tab-only) or ``create_service_for`` (named tab).
        """
        tab = self._bootstrap_default_tab()
        if tab is None:
            logger.debug("[startup-service] '%s' → no bootstrap tab", service_id)
            return None
        method = getattr(tab, "create_service", None)
        if method is None:
            return None
        try:
            result = method(service_id, *args, **kwargs)
        except Exception:
            logger.exception(
                "Startup service probe failed for %r on %s",
                service_id,
                tab.session_type,
            )
            raise
        logger.debug(
            "[startup-service] '%s' → %s from %s",
            service_id,
            type(result).__name__ if result is not None else "None",
            tab.session_type,
        )
        return result

    def notify_all(self, hook_id: str, *args: Any, **kwargs: Any) -> None:
        """Call a tab-owned hook on every registered tab, regardless of which
        one is active.

        For hooks that are genuinely global broadcasts rather than
        session-scoped requests — e.g. ``install_translations`` (each tab
        binds its own UI's translation signals at startup, not just the
        active one's) or ``refresh_startup_button_visuals`` (a cosmetic
        startup refresh every tab's page should get). Do not use this for
        anything that reads or mutates session state; those must go through
        ``create_service``/``create_main_window_feature``, which resolve
        only against the active tab. See docs/dev/tabs/capability-mechanisms.md.

        Return values are not collected — this is fire-and-forget by design,
        matching every current caller. One tab's hook raising does not stop
        the others; the exception is logged and swallowed per-tab.
        """
        for tab in self._tabs.values():
            try:
                tab.create_service(hook_id, *args, **kwargs)
            except Exception:
                logger.exception(
                    "Tab broadcast hook failed for %s on %s", hook_id, tab.session_type
                )

    def assemble_host_pages(self, ui: Any) -> None:
        """Let registered tabs assemble any legacy host-owned page pieces.

        Skips tabs whose pages haven't been created yet (lazy init — the
        page will be assembled when ``_ensure_page`` creates it).
        """
        self._ui = ui
        for session_type, tab in self._tabs.items():
            if session_type not in self._pages:
                continue
            try:
                tab.assemble_host_page(ui)
            except Exception:
                logger.exception("Tab host-page assembly failed for %s", session_type)
                raise

    def finalize_host_pages(self, ui: Any) -> None:
        """Let registered tabs do one-time cosmetic setup on their own host-assembled chrome.

        Only the currently active tab's page is guaranteed to exist (created
        lazily by ``activate()``).  Other tabs are skipped — their
        ``finalize_host_page`` runs when they are first shown.
        """
        active_type = self._active_session_type
        if active_type is None:
            return
        tab = self._tabs.get(active_type)
        if tab is None:
            return
        try:
            tab.finalize_host_page(ui)
        except Exception:
            logger.exception("Tab host-page finalize failed for %s", active_type)
            raise

    def apply_host_session_mode(
        self,
        session_type: str,
        ui: Any,
        session_title: str | None = None,
    ) -> bool:
        tab = self._tabs.get(session_type)
        if tab is None:
            return False
        try:
            return bool(tab.apply_host_session_mode(ui, session_title=session_title))
        except Exception:
            logger.exception("Tab host session-mode hook failed for %s", session_type)
            raise

    def install_pages(
        self,
        stack: QStackedWidget,
        context: TabContext,
    ) -> None:
        """Register tab types without creating pages (lazy initialization).

        Pages are created on-demand when a tab is first shown via
        ``activate()`` → ``_ensure_page()``.  This avoids building 30+
        widgets for tabs the user may never visit.
        """
        self._context = context
        self._stack = stack
        self.contribute_all_settings()
        self.contribute_all_help()
        for session_type, tab in self._tabs.items():
            if session_type not in self._pages:
                self._pending_pages[session_type] = tab

    def _ensure_page(self, session_type: str) -> QWidget | None:
        """Create and assemble the page for *session_type* if not yet done.

        Returns the page widget (or ``None`` if the tab is unknown).
        """
        if session_type in self._pages:
            return self._pages[session_type]
        tab = self._pending_pages.pop(session_type, None) or self._tabs.get(session_type)
        if tab is None:
            return None
        return self._create_and_assemble_page(session_type, tab)

    def _create_and_assemble_page(
        self, session_type: str, tab: TabContract
    ) -> QWidget | None:
        """Create a page widget, add it to the stack, and assemble host pieces."""
        stack = getattr(self, "_stack", None)
        if stack is None or self._context is None:
            return None
        try:
            page = tab.create_page(stack, self._context)
            stack.addWidget(page)
            self._pages[session_type] = page
        except Exception as e:
            logger.error("Failed to create page for tab '%s': %s", session_type, e)
            return None
        try:
            ui = getattr(self, "_ui", None)
            if ui is not None:
                tab.assemble_host_page(ui)
        except Exception:
            logger.exception("Tab host-page assembly failed for %s", session_type)
        try:
            ui = getattr(self, "_ui", None)
            if ui is not None:
                tab.finalize_host_page(ui)
        except Exception:
            logger.exception("Tab host-page finalize failed for %s", session_type)
        self.contribute_settings_for(session_type)
        self.contribute_all_help()
        return page

    def install_missing_pages(self, stack: QStackedWidget) -> tuple[str, ...]:
        """Register deferred tabs without creating pages (lazy init).

        Pages will be created on-demand when each tab is first shown.
        """
        if self._context is None:
            raise RuntimeError("TabContext not set; call install_pages first")
        self._stack = stack
        added: list[str] = []
        for session_type, tab in self._tabs.items():
            if session_type in self._pages or session_type in self._pending_pages:
                continue
            self._pending_pages[session_type] = tab
            added.append(session_type)
        return tuple(added)

    def get_page(self, session_type: str) -> QWidget | None:
        return self._pages.get(session_type)

    def bootstrap_default_tab(self) -> "TabContract | None":
        """Public accessor for whichever registered tab declares
        `TabContract.is_bootstrap_default = True`.

        The role is reserved exclusively for ``session_picker`` (the tab
        behind `core.store.INITIAL_WORKSPACE_SESSION_TYPE`); any other tab
        claiming it is a registration bug and fails loudly. Legacy
        main-window shell wiring (toolbar, export, ``image_canvas``, …)
        routes by capability, not this flag.
        """
        return self._bootstrap_default_tab()

    def _bootstrap_default_tab(self) -> "TabContract | None":
        """Return the sole registered tab with `is_bootstrap_default = True`.

        `None` if no tab claims the role, or if more than one does (logs an
        error in the latter case — that's a registration bug, not a runtime
        condition to silently resolve). A non-``session_picker`` claimant is
        a hard error: the role is reserved exclusively for the tab behind
        `core.store.INITIAL_WORKSPACE_SESSION_TYPE`.
        """
        from core.store import INITIAL_WORKSPACE_SESSION_TYPE

        candidates = [tab for tab in self._tabs.values() if tab.is_bootstrap_default]
        if not candidates:
            logger.error("TabRegistry: no tab claims is_bootstrap_default")
            return None
        if len(candidates) > 1:
            logger.error(
                "TabRegistry: multiple tabs claim is_bootstrap_default: %s",
                [t.session_type for t in candidates],
            )
            return None
        tab = candidates[0]
        if tab.session_type != INITIAL_WORKSPACE_SESSION_TYPE:
            logger.error(
                "TabRegistry: is_bootstrap_default reserved for '%s' but "
                "'%s' claimed it — bootstrap default is the initial "
                "workspace session only",
                INITIAL_WORKSPACE_SESSION_TYPE,
                tab.session_type,
            )
            raise RuntimeError(
                f"is_bootstrap_default reserved for '{INITIAL_WORKSPACE_SESSION_TYPE}' "
                f"but '{tab.session_type}' claimed it"
            )
        return tab

    def _first_tab_answering(
        self, method_name: str, *args: Any, **kwargs: Any
    ) -> "TabContract | None":
        """Return the first registered tab (in registration order — bootstrap
        before deferred) whose ``method_name`` returns a non-``None`` value
        for the given args.

        Used by ``create_startup_service``/``create_main_window_feature`` to
        route legacy shell wiring by capability instead of by a privileged
        tab role: the tab that actually implements the service/feature answers
        it. ``method_name`` must be a callable attribute on ``TabContract``
        that returns ``None`` for "not mine" (``create_service`` /
        ``create_main_window_feature`` both satisfy this). Returns ``None``
        when no tab answers.

        Note: this probes by *calling* the method, which already runs the
        tab's implementation (side effects included) — prefer
        ``_first_tab_answering_result`` so the result is not built twice.
        """
        answered = self._first_tab_answering_result(method_name, *args, **kwargs)
        return answered[0] if answered is not None else None

    def _first_tab_answering_result(
        self, method_name: str, *args: Any, **kwargs: Any
    ) -> tuple["TabContract", object] | None:
        """Probe tabs for the first non-``None`` answer, returning the result.

        The probe *is* the real call (tab implementations create their
        service/feature during it), so callers must use the returned result
        instead of invoking ``method_name`` a second time — a second call
        would build a duplicate instance and re-run its side effects
        (e.g. re-registering a context menu provider → duplicated menu
        sections). See docs/dev/tabs/capability-mechanisms.md.
        """
        for tab in self._tabs.values():
            method = getattr(tab, method_name, None)
            if method is None:
                continue
            try:
                result = method(*args, **kwargs)
            except Exception:
                logger.exception(
                    "Tab %s probe failed for %r on %s",
                    method_name,
                    args[0] if args else kwargs,
                    tab.session_type,
                )
                raise
            if result is not None:
                return tab, result
        return None

    def activate_default(self) -> None:
        """Activate whichever registered tab declares
        `TabContract.is_bootstrap_default = True` (exclusively
        ``session_picker``).

        Used once during startup to seed `_active_session_type` for the
        narrow window before any workspace session exists (see
        `ui/main_window/layouts.py`). No-op if no tab claims the role, or if
        more than one does.
        """
        tab = self._bootstrap_default_tab()
        if tab is not None:
            self.activate(tab.session_type)

    def activate(self, session_type: str) -> None:
        if session_type != self._active_session_type:
            if self._active_session_type is not None:
                self.deactivate(self._active_session_type)
            self._ensure_page(session_type)
            tab = self._tabs.get(session_type)
            if tab and self._context:
                try:
                    tab.on_activated(self._context)
                    self._active_session_type = session_type
                except Exception as e:
                    logger.error(f"Tab activate error ({session_type}): {e}")
        self._sync_active_session_for_type(session_type)

    def _sync_active_session_for_type(self, session_type: str) -> None:
        if session_type != self._active_session_type or self._context is None:
            return
        session_id = self._resolve_active_session_id(session_type)
        if session_id is None or session_id == self._active_session_id:
            return
        self.notify_active_session_changed(
            session_id,
            session_type,
            self._active_session_id,
        )

    def _resolve_active_session_id(self, session_type: str) -> str | None:
        store = getattr(self._context, "store", None) if self._context else None
        if store is None:
            return None
        try:
            session = store.get_active_workspace_session()
        except Exception:
            return None
        if session is None or getattr(session, "session_type", None) != session_type:
            return None
        return getattr(session, "id", None)

    def notify_active_session_changed(
        self,
        session_id: str,
        session_type: str,
        previous_session_id: str | None = None,
    ) -> None:
        if session_type != self._active_session_type:
            return
        if session_id == self._active_session_id:
            return
        tab = self._tabs.get(session_type)
        if tab is None or self._context is None:
            return
        try:
            tab.on_active_session_changed(session_id, self._context)
            self._active_session_id = session_id
        except Exception as e:
            logger.error(
                "Tab on_active_session_changed error (%s): %s",
                session_type,
                e,
            )

    def deactivate(self, session_type: str) -> None:
        tab = self._tabs.get(session_type)
        if tab and self._context:
            try:
                tab.on_deactivated(self._context)
            except Exception as e:
                logger.error(f"Tab deactivate error ({session_type}): {e}")
        if self._active_session_type == session_type:
            self._active_session_type = None
            self._active_session_id = None

    def notify_session_created(self, session_type: str, session_id: str) -> None:
        tab = self._tabs.get(session_type)
        if tab and self._context:
            try:
                tab.on_session_created(session_id, self._context)
            except Exception as e:
                logger.error(f"Tab on_session_created error ({session_type}): {e}")

    def serialize_session(self, session_type: str, session_id: str) -> dict[str, Any] | None:
        """Ask the owning tab for a project-save snapshot of this session.

        Returns None if the tab isn't registered or doesn't support project
        persistence (default `TabContract.serialize_session` returns None).
        """
        tab = self._tabs.get(session_type)
        if tab is None or self._context is None:
            return None
        try:
            return tab.serialize_session(session_id, self._context)
        except Exception:
            logger.exception("Tab serialize_session failed for %s", session_type)
            return None

    def collect_pixel_cache_sources(
        self, session_type: str, session_id: str
    ) -> dict[str, Any]:
        """Ask the owning tab for live open ``TiledPixelStore`` sources to
        embed as a decode-skip cache. Default `{}` (opt-in per tab)."""
        tab = self._tabs.get(session_type)
        if tab is None or self._context is None:
            return {}
        try:
            return tab.collect_pixel_cache_sources(session_id, self._context)
        except Exception:
            logger.exception("Tab collect_pixel_cache_sources failed for %s", session_type)
            return {}

    def deserialize_session(
        self, session_type: str, session_id: str, data: dict[str, Any]
    ) -> None:
        """Ask the owning tab to restore a session from a project-save snapshot."""
        tab = self._tabs.get(session_type)
        if tab is None or self._context is None:
            return
        try:
            tab.deserialize_session(session_id, data, self._context)
        except Exception:
            logger.exception("Tab deserialize_session failed for %s", session_type)

    def rehydrate_session(self, session_type: str, session_id: str) -> None:
        tab = self._tabs.get(session_type)
        if tab is None or self._context is None:
            return
        try:
            tab.rehydrate_session(session_id, self._context)
        except Exception:
            logger.exception("Tab rehydrate_session failed for %s", session_type)

    def duplicate_session(
        self, session_type: str, source_session_id: str
    ) -> dict[str, Any] | None:
        tab = self._tabs.get(session_type)
        if tab is None or self._context is None:
            return None
        try:
            return tab.duplicate_session(source_session_id, self._context)
        except Exception:
            logger.exception("Tab duplicate_session failed for %s", session_type)
            return None

    def notify_session_closed(self, session_type: str, session_id: str) -> None:
        tab = self._tabs.get(session_type)
        if tab and self._context:
            try:
                tab.on_session_closed(session_id, self._context)
            except Exception as e:
                logger.error(f"Tab on_session_closed error ({session_type}): {e}")

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
        """Refresh theme-owned chrome; skip hidden workspace pages.

        Hidden tabs (e.g. Image Compare while the session picker is up) are
        marked stale and flushed on the next ``flush_stale_appearance`` /
        session switch — theme flips stay responsive.
        """
        ui = getattr(host_window, "ui", None)
        stack = getattr(ui, "workspace_stack", None)
        current = stack.currentWidget() if stack is not None else None
        for session_type, tab in self._tabs.items():
            page = self._pages.get(session_type)
            if (
                current is not None
                and page is not None
                and page is not current
            ):
                self._appearance_stale.add(session_type)
                continue
            try:
                tab.apply_appearance(host_window)
                self._appearance_stale.discard(session_type)
            except Exception as e:
                logger.error(f"Tab appearance error ({tab.session_type}): {e}")

    def flush_stale_appearance(self, host_window) -> None:
        """Apply deferred theme chrome for the currently visible tab page."""
        if not self._appearance_stale:
            return
        ui = getattr(host_window, "ui", None)
        stack = getattr(ui, "workspace_stack", None)
        current = stack.currentWidget() if stack is not None else None
        if current is None:
            return
        for session_type in tuple(self._appearance_stale):
            if self._pages.get(session_type) is not current:
                continue
            tab = self._tabs.get(session_type)
            if tab is None:
                self._appearance_stale.discard(session_type)
                continue
            try:
                tab.apply_appearance(host_window)
                self._appearance_stale.discard(session_type)
            except Exception as e:
                logger.error(f"Tab appearance flush error ({session_type}): {e}")

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