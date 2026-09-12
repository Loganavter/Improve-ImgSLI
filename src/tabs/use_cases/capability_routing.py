"""TabRegistry use_cases: service/feature creation and broadcast hooks.

See docs/dev/tabs/capability-mechanisms.md for the routing rules these
functions implement (active-tab-only vs. named-tab vs. by-capability).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tabs.contract import TabContract
    from tabs.registry import TabRegistry

logger = logging.getLogger("ImproveImgSLI")


def collect_help_contributions(registry: "TabRegistry") -> list[Any]:
    """Collectors: gather typed ``HelpContribution`` return values (broadcast).

    Replaces ``notify_all("contribute_help", registry)`` fire-and-forget.
    Per-tab exception is logged and does not stop other tabs.
    """
    from plugins.help.contribution import HelpContribution

    contributions: list[Any] = []
    for tab in registry._tabs.values():
        try:
            result = tab.create_service("contribute_help")
        except Exception:
            logger.exception("help contribution failed for %s", tab.session_type)
            continue
        if result is None:
            continue
        # Legacy fire-and-forget returned ``True`` after mutating registry
        if isinstance(result, bool):
            continue
        items: list[Any]
        if isinstance(result, (list, tuple)):
            items = list(result)
        else:
            items = [result]
        for item in items:
            if not isinstance(item, HelpContribution):
                logger.warning(
                    "tab %s returned non-HelpContribution for contribute_help: %r",
                    tab.session_type,
                    type(item).__name__,
                )
                continue
            expected = tab.i18n_namespace or tab.session_type
            if item.owner_tab != expected:
                logger.warning(
                    "tab %s contribute_help owner_tab mismatch: %r vs expected %r",
                    tab.session_type,
                    item.owner_tab,
                    expected,
                )
            contributions.append(item)
    return contributions


def collect_settings_contributions(registry: "TabRegistry") -> list[Any]:
    """Collectors: gather typed ``SettingsContribution`` return values (broadcast).

    Replaces ``notify_all("contribute_settings", registry)`` fire-and-forget.
    Per-tab exception is logged and does not stop other tabs.
    """
    from plugins.settings.registry import SettingsContribution

    contributions: list[Any] = []
    for tab in registry._tabs.values():
        try:
            result = tab.create_service("contribute_settings")
        except Exception:
            logger.exception("settings contribution failed for %s", tab.session_type)
            continue
        if result is None:
            continue
        if isinstance(result, bool):
            # Legacy shim: tab mutated registry and returned True — no typed object
            continue
        items: list[Any]
        if isinstance(result, (list, tuple)):
            items = list(result)
        else:
            items = [result]
        for item in items:
            if not isinstance(item, SettingsContribution):
                logger.warning(
                    "tab %s returned non-SettingsContribution for contribute_settings: %r",
                    tab.session_type,
                    type(item).__name__,
                )
                continue
            expected = tab.i18n_namespace or tab.session_type
            if item.owner_tab != expected:
                logger.warning(
                    "tab %s contribute_settings owner_tab mismatch: %r vs expected %r",
                    tab.session_type,
                    item.owner_tab,
                    expected,
                )
            contributions.append(item)
    return contributions


def contribute_all_settings(registry: "TabRegistry") -> None:
    """Let every registered tab publish settings sections (broadcast).

    Collect typed ``SettingsContribution`` objects and install them immutably.
    Per-tab exception is logged; one tab failing does not stop others.
    """
    from plugins.settings.registry import install_settings_contributions

    contributions = collect_settings_contributions(registry)
    if contributions:
        install_settings_contributions(contributions)


def contribute_all_help(registry: "TabRegistry") -> None:
    """Collect tab Help subtrees and install them into the host tree.

    Collect typed ``HelpContribution`` objects and install them immutably.
    Per-tab exception is logged; one tab failing does not stop others.
    """
    from plugins.help.tree import install_help_contributions

    contributions = collect_help_contributions(registry)
    if contributions:
        install_help_contributions(contributions)


def contribute_settings_for(registry: "TabRegistry", session_type: str) -> None:
    """Publish settings for one tab (e.g. after late discovery)."""
    tab = registry._tabs.get(session_type)
    if tab is None:
        return
    from plugins.settings.registry import SettingsContribution, install_settings_contributions

    try:
        result = tab.create_service("contribute_settings")
    except Exception as e:
        logger.error(f"contribute_settings failed for {session_type}: {e}")
        return
    if result is None:
        return
    if isinstance(result, bool):
        # Legacy shim: tab already mutated registry elsewhere
        return
    contributions: list[SettingsContribution]
    if isinstance(result, (list, tuple)):
        contributions = [r for r in result if isinstance(r, SettingsContribution)]
    elif isinstance(result, SettingsContribution):
        contributions = [result]
    else:
        logger.warning("tab %s contribute_settings returned non-SettingsContribution: %r", session_type, type(result).__name__)
        return
    if contributions:
        install_settings_contributions(contributions)


def create_main_window_feature(
    registry: "TabRegistry", feature_id: str, **kwargs: Any
) -> Any:
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
    answered = _first_tab_answering_result(
        registry, "create_main_window_feature", feature_id, **kwargs
    )
    if answered is None:
        return None
    # Same as create_startup_service: the probe already built the feature,
    # never call create_main_window_feature a second time.
    _tab, result = answered
    return result


def create_service(
    registry: "TabRegistry", service_id: str, *args: Any, **kwargs: Any
) -> Any:
    """Create a service owned by the active tab.

    Resolves strictly against the tab matching ``registry._active_session_type``
    — never any other registered tab. Returns ``None`` (not another
    tab's answer) if the active tab doesn't implement ``service_id``.
    See docs/dev/tabs/capability-mechanisms.md.
    """
    active = registry._active_session_type
    if active is None:
        return None
    tab = registry._tabs.get(active)
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
    registry: "TabRegistry",
    session_type: str,
    service_id: str,
    *args: Any,
    **kwargs: Any,
) -> Any:
    """Create a service owned by a specific tab (not necessarily active).

    For host chrome that addresses a known hub tab by ``session_type``
    (typically ``core.store.INITIAL_WORKSPACE_SESSION_TYPE``). Prefer
    ``create_service`` when the capability belongs to the *active*
    session. Returns ``None`` if that tab is missing or does not
    implement ``service_id``. See docs/dev/tabs/capability-mechanisms.md.
    """
    tab = registry._tabs.get(session_type)
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


def create_startup_service(
    registry: "TabRegistry", service_id: str, *args: Any, **kwargs: Any
) -> Any:
    """Create a legacy startup-shell service from whichever tab provides it.

    Like ``create_main_window_feature``, this is *not* routed by the
    currently active session — it is requested synchronously during
    one-time main-window shell construction, before the user's real
    initial session is necessarily active (see
    ``create_main_window_feature``'s docstring for why routing by
    active session would be wrong here).

    Routes **by capability**: each already-discovered tab is asked in
    registration order (bootstrap before deferred) and the first one
    whose ``create_service`` returns a non-``None`` answer provides the
    service. No tab has a privileged role — ``image_compare`` answers
    most of today's legacy shell capabilities purely because it is the
    tab that implements them, not because it is bootstrap-default.
    See docs/dev/tabs/capability-mechanisms.md.

    For capabilities needed after startup, use ``create_service``
    (active-tab-only) or ``create_service_for`` (named tab).
    """
    answered = _first_tab_answering_result(
        registry, "create_service", service_id, *args, **kwargs
    )
    if answered is None:
        logger.debug("[startup-service] '%s' → None (unclaimed)", service_id)
        return None
    tab, result = answered
    logger.debug(
        "[startup-service] '%s' → %s from %s",
        service_id,
        type(result).__name__,
        tab.session_type,
    )
    return result


def notify_all(registry: "TabRegistry", hook_id: str, *args: Any, **kwargs: Any) -> None:
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
    for tab in registry._tabs.values():
        try:
            tab.create_service(hook_id, *args, **kwargs)
        except Exception:
            logger.exception(
                "Tab broadcast hook failed for %s on %s", hook_id, tab.session_type
            )


def _first_tab_answering(
    registry: "TabRegistry", method_name: str, *args: Any, **kwargs: Any
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
    answered = _first_tab_answering_result(registry, method_name, *args, **kwargs)
    return answered[0] if answered is not None else None


def _first_tab_answering_result(
    registry: "TabRegistry", method_name: str, *args: Any, **kwargs: Any
) -> "tuple[TabContract, object] | None":
    """Probe tabs for the first non-``None`` answer, returning the result.

    The probe *is* the real call (tab implementations create their
    service/feature during it), so callers must use the returned result
    instead of invoking ``method_name`` a second time — a second call
    would build a duplicate instance and re-run its side effects
    (e.g. re-registering a context menu provider → duplicated menu
    sections). See docs/dev/tabs/capability-mechanisms.md.
    """
    for tab in registry._tabs.values():
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
