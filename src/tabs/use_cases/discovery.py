"""TabRegistry use_cases: discovering and importing tab implementations."""

from __future__ import annotations

import importlib
import logging
import pkgutil
from pathlib import Path
from typing import TYPE_CHECKING

from core.plugin_system.discovery_scan import tab_packages_for_tier
from resources.translations import add_i18n_root
from tabs.contract import TabContract
from core.log_names import APP_LOGGER_NAME

if TYPE_CHECKING:
    from tabs.registry import TabDiscoveryTier, TabRegistry

logger = logging.getLogger(APP_LOGGER_NAME)


def discover(registry: "TabRegistry", *, tier: "TabDiscoveryTier | None" = None) -> None:
    """Discover tab implementations from the ``tabs/`` package.

    Idempotent per tier. ``tier=None`` ensures bootstrap then deferred
    tabs (preserves defensive ``discover()`` at ~25 call sites).
    """
    if tier is None:
        discover(registry, tier="bootstrap")
        discover(registry, tier="deferred")
        return

    from core.startup_trace import startup_mark

    if tier in registry._discovered_tiers:
        return

    if tier == "all":
        _discover_all_modules(registry)
    else:
        modules = tab_packages_for_tier(tier)
        for module_name in modules:
            _discover_tab_module(registry, module_name)

    registry._discovered_tiers.add(tier)
    startup_mark(f"tab.discover.{tier}")


def _discover_all_modules(registry: "TabRegistry") -> None:
    try:
        import tabs as tabs_pkg
    except ImportError:
        return

    tabs_path = Path(tabs_pkg.__path__[0])

    for finder, module_name, is_pkg in pkgutil.iter_modules(tabs_pkg.__path__):
        if module_name.startswith("_") or module_name in ("contract", "registry"):
            continue
        _discover_tab_module(registry, module_name, tabs_path=tabs_path)


def _discover_tab_module(
    registry: "TabRegistry", module_name: str, *, tabs_path: Path | None = None
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
                if instance.session_type in registry._tabs:
                    # Fail loud: two tabs claiming one routing key means one
                    # of them is unreachable. Keep the first (stable routing),
                    # but log at error so the collision cannot hide.
                    existing = registry._tabs[instance.session_type]
                    logger.error(
                        "Duplicate session_type '%s': %s ignored, %s kept",
                        instance.session_type,
                        type(instance).__name__,
                        type(existing).__name__,
                    )
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
                registry._tabs[instance.session_type] = instance
    except Exception:
        # Per-module containment: one broken tab (bad import, bad ctor, bad
        # tier) hides only itself. Catching Exception — not just
        # (ImportError, AttributeError) — keeps a single tab's RuntimeError
        # from aborting the whole tier loop and hiding every later tab.
        logger.exception(
            "TabRegistry: failed to import/register tabs.%s.tab",
            module_name,
        )
