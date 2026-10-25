"""Collect the keymap-defaults catalog (metadata only, no live widgets).

Settings → Keyboard and the apply path both need every action's *default*
chord and tab owner without instantiating a tab page. The live pages never
expose that (their catalogs are built from live widgets), so tabs publish the
metadata through ``contribute_keymap_defaults`` — this module is the single
collector for both call sites.

Split out of ``plugins/settings/pages/keyboard.py`` (page chrome vs catalog
collection: two concerns, and the page is at its file-size budget).
"""

from __future__ import annotations

import logging

from ui.actions.keymap import KeymapDefaultsRegistry

logger = logging.getLogger(__name__)


def collect_keymap_defaults() -> KeymapDefaultsRegistry:
    """Every platform + tab keymap default row (never raises)."""
    registry = KeymapDefaultsRegistry()
    from ui.actions.platform import contribute_platform_keymap_defaults

    try:
        from core.store import INITIAL_WORKSPACE_SESSION_TYPE
        from tabs.registry import TabRegistry

        tabs = TabRegistry()
        tabs.discover()
        new_session_types = [
            tab.session_type
            for tab in tabs.list_tabs()
            if tab.session_type != INITIAL_WORKSPACE_SESSION_TYPE
        ]
        contribute_platform_keymap_defaults(registry, new_session_types)
        tabs.notify_all("contribute_keymap_defaults", registry)
    except Exception:
        logger.exception(
            "Failed to collect tab keymap defaults for Settings → Keyboard"
        )
        contribute_platform_keymap_defaults(registry)
    return registry
