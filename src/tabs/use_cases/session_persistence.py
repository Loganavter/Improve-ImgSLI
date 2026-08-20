"""TabRegistry use_cases: project-save session persistence hooks."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tabs.registry import TabRegistry

logger = logging.getLogger("ImproveImgSLI")


def notify_session_created(registry: "TabRegistry", session_type: str, session_id: str) -> None:
    tab = registry._tabs.get(session_type)
    if tab and registry._context:
        try:
            tab.on_session_created(session_id, registry._context)
        except Exception as e:
            logger.error(f"Tab on_session_created error ({session_type}): {e}")


def serialize_session(
    registry: "TabRegistry", session_type: str, session_id: str
) -> dict[str, Any] | None:
    """Ask the owning tab for a project-save snapshot of this session.

    Returns None if the tab isn't registered or doesn't support project
    persistence (default `TabContract.serialize_session` returns None).
    """
    tab = registry._tabs.get(session_type)
    if tab is None or registry._context is None:
        return None
    try:
        return tab.serialize_session(session_id, registry._context)
    except Exception:
        logger.exception("Tab serialize_session failed for %s", session_type)
        return None


def collect_pixel_cache_sources(
    registry: "TabRegistry", session_type: str, session_id: str
) -> dict[str, Any]:
    """Ask the owning tab for live open ``TiledPixelStore`` sources to
    embed as a decode-skip cache. Default `{}` (opt-in per tab)."""
    tab = registry._tabs.get(session_type)
    if tab is None or registry._context is None:
        return {}
    try:
        return tab.collect_pixel_cache_sources(session_id, registry._context)
    except Exception:
        logger.exception("Tab collect_pixel_cache_sources failed for %s", session_type)
        return {}


def deserialize_session(
    registry: "TabRegistry", session_type: str, session_id: str, data: dict[str, Any]
) -> None:
    """Ask the owning tab to restore a session from a project-save snapshot."""
    tab = registry._tabs.get(session_type)
    if tab is None or registry._context is None:
        return
    try:
        tab.deserialize_session(session_id, data, registry._context)
    except Exception:
        logger.exception("Tab deserialize_session failed for %s", session_type)


def rehydrate_session(registry: "TabRegistry", session_type: str, session_id: str) -> None:
    tab = registry._tabs.get(session_type)
    if tab is None or registry._context is None:
        return
    try:
        tab.rehydrate_session(session_id, registry._context)
    except Exception:
        logger.exception("Tab rehydrate_session failed for %s", session_type)


def duplicate_session(
    registry: "TabRegistry", session_type: str, source_session_id: str
) -> dict[str, Any] | None:
    tab = registry._tabs.get(session_type)
    if tab is None or registry._context is None:
        return None
    try:
        return tab.duplicate_session(source_session_id, registry._context)
    except Exception:
        logger.exception("Tab duplicate_session failed for %s", session_type)
        return None


def notify_session_closed(registry: "TabRegistry", session_type: str, session_id: str) -> None:
    tab = registry._tabs.get(session_type)
    if tab and registry._context:
        try:
            tab.on_session_closed(session_id, registry._context)
        except Exception as e:
            logger.error(f"Tab on_session_closed error ({session_type}): {e}")
