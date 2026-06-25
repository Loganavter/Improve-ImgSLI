"""Auto-discovery of settings sections.

Every module in this package that defines a module-level ``SECTION``
(``SettingsSection`` instance) or ``SECTIONS`` (iterable of them) is picked up
and registered with the global settings registry. Add a new ``.py`` file here
to contribute a sidebar page — no other wiring required.
"""

from __future__ import annotations

import importlib
import logging
import pkgutil

logger = logging.getLogger("ImproveImgSLI")


def discover_and_register(registry) -> None:
    package_name = __name__
    package_path = __path__  # type: ignore[name-defined]
    for _finder, module_name, is_pkg in pkgutil.iter_modules(package_path):
        if is_pkg or module_name.startswith("_"):
            continue
        full_name = f"{package_name}.{module_name}"
        try:
            module = importlib.import_module(full_name)
        except Exception as exc:
            logger.error("Settings page %s failed to import: %s", full_name, exc)
            continue
        section = getattr(module, "SECTION", None)
        if section is not None:
            registry.add(section)
        for s in getattr(module, "SECTIONS", ()) or ():
            registry.add(s)
