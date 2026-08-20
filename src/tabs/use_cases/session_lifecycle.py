"""TabRegistry use_cases: session activation lifecycle."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from tabs.use_cases import pages

if TYPE_CHECKING:
    from tabs.contract import TabContract
    from tabs.registry import TabRegistry

logger = logging.getLogger("ImproveImgSLI")


def bootstrap_default_tab(registry: "TabRegistry") -> "TabContract | None":
    """Public accessor for whichever registered tab declares
    `TabContract.is_bootstrap_default = True`.

    The role is reserved exclusively for ``session_picker`` (the tab
    behind `core.store.INITIAL_WORKSPACE_SESSION_TYPE`); any other tab
    claiming it is a registration bug and fails loudly. Legacy
    main-window shell wiring (toolbar, export, ``image_canvas``, …)
    routes by capability, not this flag.
    """
    return _bootstrap_default_tab(registry)


def _bootstrap_default_tab(registry: "TabRegistry") -> "TabContract | None":
    """Return the sole registered tab with `is_bootstrap_default = True`.

    `None` if no tab claims the role, or if more than one does (logs an
    error in the latter case — that's a registration bug, not a runtime
    condition to silently resolve). A non-``session_picker`` claimant is
    a hard error: the role is reserved exclusively for the tab behind
    `core.store.INITIAL_WORKSPACE_SESSION_TYPE`.
    """
    from core.store import INITIAL_WORKSPACE_SESSION_TYPE

    candidates = [tab for tab in registry._tabs.values() if tab.is_bootstrap_default]
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


def activate_default(registry: "TabRegistry") -> None:
    """Activate whichever registered tab declares
    `TabContract.is_bootstrap_default = True` (exclusively
    ``session_picker``).

    Used once during startup to seed `_active_session_type` for the
    narrow window before any workspace session exists (see
    `ui/main_window/layouts.py`). No-op if no tab claims the role, or if
    more than one does.
    """
    tab = _bootstrap_default_tab(registry)
    if tab is not None:
        activate(registry, tab.session_type)


def activate(registry: "TabRegistry", session_type: str) -> None:
    if session_type != registry._active_session_type:
        if registry._active_session_type is not None:
            deactivate(registry, registry._active_session_type)
        pages._ensure_page(registry, session_type)
        tab = registry._tabs.get(session_type)
        if tab and registry._context:
            try:
                tab.on_activated(registry._context)
                registry._active_session_type = session_type
            except Exception as e:
                logger.error(f"Tab activate error ({session_type}): {e}")
    _sync_active_session_for_type(registry, session_type)


def _sync_active_session_for_type(registry: "TabRegistry", session_type: str) -> None:
    if session_type != registry._active_session_type or registry._context is None:
        return
    session_id = _resolve_active_session_id(registry, session_type)
    if session_id is None or session_id == registry._active_session_id:
        return
    notify_active_session_changed(
        registry,
        session_id,
        session_type,
        registry._active_session_id,
    )


def _resolve_active_session_id(registry: "TabRegistry", session_type: str) -> str | None:
    store = getattr(registry._context, "store", None) if registry._context else None
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
    registry: "TabRegistry",
    session_id: str,
    session_type: str,
    previous_session_id: str | None = None,
) -> None:
    if session_type != registry._active_session_type:
        return
    if session_id == registry._active_session_id:
        return
    tab = registry._tabs.get(session_type)
    if tab is None or registry._context is None:
        return
    try:
        tab.on_active_session_changed(session_id, registry._context)
        registry._active_session_id = session_id
    except Exception as e:
        logger.error(
            "Tab on_active_session_changed error (%s): %s",
            session_type,
            e,
        )


def deactivate(registry: "TabRegistry", session_type: str) -> None:
    tab = registry._tabs.get(session_type)
    if tab and registry._context:
        try:
            tab.on_deactivated(registry._context)
        except Exception as e:
            logger.error(f"Tab deactivate error ({session_type}): {e}")
    if registry._active_session_type == session_type:
        registry._active_session_type = None
        registry._active_session_id = None
