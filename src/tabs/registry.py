"""Tab registry — auto-discovers and manages workspace tabs."""

from __future__ import annotations

import importlib
import logging
import pkgutil
from pathlib import Path
from typing import Any

from PySide6.QtWidgets import QStackedWidget, QWidget

from tabs.contract import TabContext, TabContract
from resources.translations import add_i18n_root

logger = logging.getLogger("ImproveImgSLI")

class TabRegistry:
    """
    Discovers tab implementations from the `tabs/` package and manages
    their lifecycle within the workspace.
    """

    def __init__(self):
        self._tabs: dict[str, TabContract] = {}
        self._pages: dict[str, QWidget] = {}
        self._context: TabContext | None = None

    @property
    def registered_types(self) -> list[str]:
        return list(self._tabs.keys())

    def discover(self) -> None:
        """Scan tabs/ package for TabContract implementations."""
        try:
            import tabs as tabs_pkg
        except ImportError:
            return

        tabs_path = Path(tabs_pkg.__path__[0])

        for finder, module_name, is_pkg in pkgutil.iter_modules(tabs_pkg.__path__):
            if module_name.startswith("_") or module_name in ("contract", "registry"):
                continue

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
                        self._tabs[instance.session_type] = instance
                        logger.debug(f"Tab discovered: {instance.session_type}")
            except (ImportError, AttributeError) as e:
                logger.debug(f"Tab module tabs.{module_name}.tab not loadable: {e}")

    def get_tab(self, session_type: str) -> TabContract | None:
        return self._tabs.get(session_type)

    def list_tabs(self) -> list[TabContract]:
        return list(self._tabs.values())

    def contribute_all_settings(self) -> None:
        """Let each registered tab register its settings sections."""
        from plugins.settings.registry import get_settings_registry
        registry = get_settings_registry()
        for tab in self._tabs.values():
            try:
                tab.contribute_settings(registry)
            except Exception as e:
                logger.error(f"contribute_settings failed for {tab.session_type}: {e}")

    def install_pages(
        self,
        stack: QStackedWidget,
        context: TabContext,
    ) -> None:
        """Create pages for all discovered tabs and add them to the stack."""
        self._context = context
        self.contribute_all_settings()
        for session_type, tab in self._tabs.items():
            try:
                page = tab.create_page(stack, context)
                stack.addWidget(page)
                self._pages[session_type] = page
                logger.debug(f"Tab page installed: {session_type}")
            except Exception as e:
                logger.error(f"Failed to create page for tab '{session_type}': {e}")

    def get_page(self, session_type: str) -> QWidget | None:
        return self._pages.get(session_type)

    def activate(self, session_type: str) -> None:
        tab = self._tabs.get(session_type)
        if tab and self._context:
            try:
                tab.on_activated(self._context)
            except Exception as e:
                logger.error(f"Tab activate error ({session_type}): {e}")

    def deactivate(self, session_type: str) -> None:
        tab = self._tabs.get(session_type)
        if tab and self._context:
            try:
                tab.on_deactivated(self._context)
            except Exception as e:
                logger.error(f"Tab deactivate error ({session_type}): {e}")

    def route_drop(self, session_type: str, paths: list) -> bool:
        """Route a file drop to the active tab. Returns True if handled."""
        tab = self._tabs.get(session_type)
        if tab is None:
            return False
        from pathlib import Path as P
        resolved = [P(p) if not isinstance(p, P) else p for p in paths]
        if tab.accepts_drop(resolved):
            tab.handle_drop(resolved)
            return True
        return False

    def dispose_all(self) -> None:
        for tab in self._tabs.values():
            try:
                tab.dispose()
            except Exception:
                pass
        self._tabs.clear()
        self._pages.clear()
