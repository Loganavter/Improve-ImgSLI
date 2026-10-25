from __future__ import annotations

import logging

from core.store import INITIAL_WORKSPACE_SESSION_TYPE
from ui.host_debug import workspace_transition_debug
from core.log_names import APP_LOGGER_NAME

logger = logging.getLogger(APP_LOGGER_NAME)


def initialize_workspace_state(presenter) -> None:
    presenter._file_dialog = None
    presenter._first_dialog_load_pending = True
    presenter._last_active_session_id = None
    presenter._last_covered_session_id = None


def configure_workspace_actions(presenter):
    # The add-tab button always opens the session picker directly (see
    # on_new_workspace_tab_requested). Button no longer embeds dropdown menus.
    pass


def on_new_workspace_tab_requested(presenter):
    if not presenter.main_controller:
        return
    try:
        presenter.main_controller.workspace.create_workspace_session(
            INITIAL_WORKSPACE_SESSION_TYPE,
            activate=True,
        )
    except Exception:
        logger.exception("on_new_workspace_tab_requested: create session_picker failed")


def ensure_session_picker_visible(presenter) -> None:
    """Activate an existing Session Picker tab, or create one if none exists.

    Used by Find Action reveal / Open Session Picker — must not spawn a
    duplicate ``session_picker`` when one is already open. The workspace-tabs
    ``+`` button still goes through ``on_new_workspace_tab_requested``.
    """
    if not presenter.main_controller:
        return
    workspace = presenter.main_controller.workspace
    sessions: tuple | list = ()
    session_manager = getattr(presenter, "session_manager", None)
    if session_manager is not None:
        try:
            sessions = session_manager.list_sessions()
        except Exception:
            sessions = ()
    for session in sessions:
        if getattr(session, "session_type", None) != INITIAL_WORKSPACE_SESSION_TYPE:
            continue
        active = (
            session_manager.get_active_session()
            if session_manager is not None
            else None
        )
        if active is not None and active.id == session.id:
            return
        try:
            workspace.switch_workspace_session(session.id)
        except Exception:
            logger.exception(
                "ensure_session_picker_visible: switch to existing picker failed"
            )
        return
    try:
        workspace.create_workspace_session(
            INITIAL_WORKSPACE_SESSION_TYPE,
            activate=True,
        )
    except Exception:
        logger.exception("ensure_session_picker_visible: create session_picker failed")


def sync_workspace_tabs(presenter):
    if not presenter.session_manager:
        return
    active = presenter.session_manager.get_active_session()
    presenter.ui.sync_workspace_tabs(
        presenter.session_manager.list_sessions(),
        active.id if active else None,
    )
    sync_session_mode(presenter)


def sync_session_mode(presenter):
    if not presenter.session_manager:
        return
    active = presenter.session_manager.get_active_session()
    session_type = active.session_type if active else INITIAL_WORKSPACE_SESSION_TYPE
    session_title = active.title if active else None
    presenter.ui.sync_session_mode(session_type, session_title)
    from ui.presenters.main_window.state import flush_stale_workspace_language

    flush_stale_workspace_language(presenter)
    # Active page may declare a higher window floor (e.g. Session Picker).
    main_window = getattr(presenter, "main_window_app", None)
    if main_window is not None and getattr(main_window, "_is_ui_stable", False):
        from ui.layout_geometry import apply_main_window_minimum

        apply_main_window_minimum(main_window)


def on_workspace_tab_changed(presenter, index: int):
    if index < 0:
        workspace_transition_debug("tab_changed ignored index=%s", index)
        return
    session_id = presenter.ui.workspace_tabs.tabData(index)
    if not (session_id and presenter.main_controller):
        logger.warning(
            "[workspace-transition] tab_changed early-out index=%s "
            "session_id=%r has_controller=%s",
            index,
            session_id,
            bool(presenter.main_controller),
        )
        return

    workspace_transition_debug(
        "tab_changed index=%s session_id=%s",
        index,
        session_id,
    )
    _dismiss_ordinary_flyouts_on_tab_change(presenter)
    # Cover runs from on_store_state_changed(workspace) so session-picker /
    # Find Action / create-session paths also get the flash (workspace tabs
    # strip is often hidden).
    presenter.main_controller.workspace.switch_workspace_session(session_id)


def _dismiss_ordinary_flyouts_on_tab_change(presenter=None) -> None:
    """Close every non-pinned flyout when the active workspace tab changes.

    Flyouts (font settings, interpolation, unified lists, ...) are all
    reparented onto a single app-wide ``OverlayLayer`` host (see
    ``sli_ui_toolkit``'s ``resolve_overlay_layer``/``OverlayLayer.attach``),
    with no notion of which logical tab created them. Nothing about a
    ``QTabWidget``/workspace-strip index change is a window (de)activation
    or an outside click, so none of the existing dismiss paths
    (``ui/managers/transient_ui_parts/closing.py``,
    ``FlyoutManager``'s own event filter) ever fire for it, and a flyout
    left open on tab A keeps rendering on top of tab B after switching.
    ``pinned`` HUDs (InfoHUD/ZoomIndicator) aren't touched here — each tab
    widget hides/resyncs its own via ``hideEvent``/``showEvent`` instead
    (see ``ImageCompareWidget``/``MultiCompareWidget``), since they need to
    reappear from current state when the tab is shown again, not just stay
    hidden.

    The unified list picker is a plain ``QWidget`` rather than a toolkit
    flyout, so hide it explicitly together with the anchored overlay
    popups — the manager's passive sweep only reaches registered flyouts.
    Toasts are deliberately untouched here: they persist across tabs and
    only repoint at the new tab's anchor (see ``sync_session_mode``'s
    toast repoint). Anchors re-sync lazily on the next show via the tab's
    own anchor sync; nothing is cached here.
    """
    from sli_ui_toolkit.managers import FlyoutManager

    manager = FlyoutManager.get_instance()
    dismiss_passive = getattr(manager, "_dismiss_passive", None)
    if callable(dismiss_passive):
        dismiss_passive()
    _hide_unified_list_on_tab_change(presenter)


def _hide_unified_list_on_tab_change(presenter=None) -> None:
    """Hide the unified list picker and anchored overlay popups on switch.

    Mirror of the toast discipline with opposite polarity: toasts persist
    and repoint, transient flyouts close. Fail-open throughout, no focus
    changes, no reparenting.
    """
    ui_manager = getattr(presenter, "ui_manager", None) if presenter is not None else None
    direct = None
    if ui_manager is not None:
        try:
            direct = getattr(ui_manager, "unified_flyout", None)
        except Exception:
            pass
    if direct is not None:
        _hide_one_unified_list(direct)
    window = _resolve_tab_switch_window(presenter, ui_manager)
    if window is None:
        return
    for picker in _unified_lists_under(window):
        if picker is not direct:
            _hide_one_unified_list(picker)
    for layer in _overlay_layers_for_hosts((window,)):
        try:
            hide_all = getattr(layer, "hide_all_popups", None)
        except Exception:
            continue
        if callable(hide_all):
            try:
                hide_all()
            except Exception:
                pass


def _hide_one_unified_list(flyout) -> None:
    """Close one unified list picker without touching focus or parenting."""
    try:
        visible = flyout.isVisible()
    except Exception:
        return
    if not visible:
        return
    try:
        close = getattr(flyout, "start_closing_animation", None)
        if callable(close):
            close()
        else:
            flyout.hide()
    except Exception:
        pass


def _resolve_tab_switch_window(presenter, ui_manager):
    """Owning window: explicit refs first, sanctioned resolver fallback."""
    candidates = []
    if presenter is not None:
        candidates.append(getattr(presenter, "main_window_app", None))
        ui = getattr(presenter, "ui", None)
        candidates.append(getattr(ui, "main_window", None) if ui is not None else None)
    if ui_manager is not None:
        candidates.append(getattr(ui_manager, "parent_widget", None))
    for candidate in candidates:
        if candidate is not None:
            return candidate
    try:
        from ui.helpers.window_resolver import find_main_window

        return find_main_window()
    except Exception:
        return None


def _unified_lists_under(window) -> list:
    """Visible unified list pickers parented under the given window."""
    try:
        from ui.widgets.unified_list_picker import UnifiedListPicker

        children = list(window.findChildren(UnifiedListPicker))
    except Exception:
        return []
    found = []
    for child in children:
        try:
            if child.isVisible():
                found.append(child)
        except Exception:
            continue
    return found


def _overlay_layers_for_hosts(hosts) -> list:
    """Overlay layers attached to the given hosts (window + content)."""
    layers = []
    seen: set[int] = set()

    def _take(layer) -> None:
        if layer is None or id(layer) in seen:
            return
        seen.add(id(layer))
        layers.append(layer)

    for host in hosts:
        try:
            _take(getattr(host, "overlay_layer", None))
            _take(getattr(host, "content_overlay_layer", None))
            ui = getattr(host, "ui", None)
            content = (
                getattr(ui, "workspace_content_widget", None)
                if ui is not None
                else None
            )
            if content is None:
                content = getattr(host, "workspace_content_widget", None)
            if content is not None:
                _take(getattr(content, "content_overlay_layer", None))
        except Exception:
            continue
    return layers


def cover_active_session_transition(presenter) -> None:
    """Cover before syncing the workspace stack to a newly active session.

    Call from the workspace store-change handler, before ``sync_session_mode``.
    """
    session_manager = getattr(presenter, "session_manager", None)
    if session_manager is None:
        return
    active = session_manager.get_active_session()
    if active is None:
        return
    last_id = getattr(presenter, "_last_covered_session_id", None)
    if last_id == active.id:
        workspace_transition_debug(
            "cover skipped: same session_id=%s",
            active.id,
        )
        return
    workspace_transition_debug(
        "active session change %r -> %r type=%r",
        last_id,
        active.id,
        getattr(active, "session_type", None),
    )
    # This fires for *every* active-session change (existing-tab click via
    # on_workspace_tab_changed, brand-new tab creation via
    # create_workspace_session(..., activate=True), programmatic switches
    # from Find Action / session picker, ...), unlike
    # on_workspace_tab_changed's own dismiss call above, which only covers
    # the "click an existing tab" path -- confirmed via IMGSLI_FLYOUT_DEBUG
    # log: opening a brand-new tab produces an "active session change" line
    # here with no matching "tab_changed" line at all, so a flyout left
    # open on the old tab never got dismissed for that path.
    _dismiss_ordinary_flyouts_on_tab_change(presenter)
    presenter._last_covered_session_id = active.id
    _cover_transition_for_session(presenter, active.id)


def _cover_transition_for_session(presenter, session_id: str) -> None:
    mask, host = _resolve_workspace_transition_mask(presenter)
    if mask is None:
        logger.warning(
            "[workspace-transition] cover aborted: mask not found "
            "(session_id=%s ui.main_window=%r main_window_app=%r)",
            session_id,
            type(getattr(getattr(presenter, "ui", None), "main_window", None)).__name__,
            type(getattr(presenter, "main_window_app", None)).__name__,
        )
        return

    hint = None
    registry = getattr(presenter.ui, "_tab_registry", None)
    session_type = _resolve_session_type(presenter, session_id)
    if registry is not None and session_type:
        tab = registry.get_tab(session_type)
        if tab is not None:
            try:
                hint = tab.transition_hint()
            except Exception:
                logger.exception("transition_hint failed for %s", session_type)

    if hint is None:
        from tabs.contract import TabTransitionHint

        hint = TabTransitionHint()
    if not hint.cover_on_enter:
        workspace_transition_debug(
            "cover skipped: cover_on_enter=False (session_type=%r)",
            session_type,
        )
        return

    stack = getattr(presenter.ui, "workspace_stack", None)
    content = getattr(presenter.ui, "workspace_content_widget", None)
    if not _cover_target_below_strip(stack, content):
        logger.warning(
            "[workspace-transition] cover skipped: target outside "
            "workspace content below the tab strip "
            "(target=%r content=%r session_type=%r)",
            type(stack).__name__ if stack is not None else None,
            type(content).__name__ if content is not None else None,
            session_type,
        )
        return
    workspace_transition_debug(
        "requesting cover session_type=%r hint=(min=%s max=%s) mask_id=%s host=%r stack=%r",
        session_type,
        hint.min_duration_ms,
        hint.max_duration_ms,
        id(mask),
        type(host).__name__ if host is not None else None,
        type(stack).__name__ if stack is not None else None,
    )
    mask.cover(
        stack,
        min_duration_ms=hint.min_duration_ms,
        max_duration_ms=hint.max_duration_ms,
        session_type=session_type,
    )


def _cover_target_below_strip(target, content) -> bool:
    """True when ``target`` lives in the content area below the tab strip.

    The transition cover may only target ``workspace_stack`` (or one of its
    children), which itself lives inside ``workspace_content_widget`` below
    the strip. A window-level target (e.g. the main window) would paint the
    mask over the strip — refuse it with a cover-skipped warning instead.

    Fail-open (True) for non-widget test doubles and when the content host
    is not built yet (startup): the mask's own None-target warning still
    applies, and legacy callers passing opaque doubles keep working.
    """
    if content is None or not hasattr(content, "parentWidget"):
        return True
    if target is None or not hasattr(target, "parentWidget"):
        return True
    node = target
    for _ in range(100):
        if node is content:
            return True
        try:
            node = node.parentWidget()
        except RuntimeError:
            return False
        if node is None:
            return False
    return False


def _resolve_workspace_transition_mask(presenter):
    """Find the host transition mask after ``ui.main_window`` reassignment."""
    candidates = []
    ui = getattr(presenter, "ui", None)
    if ui is not None:
        candidates.append(getattr(ui, "main_window", None))
    candidates.append(getattr(presenter, "main_window_app", None))
    for window in candidates:
        if window is None:
            continue
        mask = getattr(window, "_workspace_transition_mask", None)
        if mask is not None:
            workspace_transition_debug(
                "mask resolved on %r id=%s",
                type(window).__name__,
                id(mask),
            )
            return mask, window
        host = getattr(window, "_app_host", None)
        if host is not None:
            mask = getattr(host, "_workspace_transition_mask", None)
            if mask is not None:
                # Migrate so later lookups hit the MainWindow directly.
                window._workspace_transition_mask = mask
                workspace_transition_debug(
                    "mask migrated from _app_host to %r id=%s",
                    type(window).__name__,
                    id(mask),
                )
                return mask, window
    workspace_transition_debug(
        "mask resolve failed candidates=%s",
        [type(c).__name__ for c in candidates if c is not None],
    )
    return None, None


def _resolve_session_type(presenter, session_id: str) -> str | None:
    manager = getattr(presenter, "session_manager", None)
    if manager is None:
        return None
    try:
        for s in manager.list_sessions():
            if getattr(s, "id", None) == session_id:
                return getattr(s, "session_type", None)
    except Exception:
        logger.exception("resolve_session_type failed for %s", session_id)
    return None


def on_workspace_tab_close_requested(presenter, index: int):
    if index < 0:
        return
    session_id = presenter.ui.workspace_tabs.tabData(index)
    if not session_id or not presenter.main_controller:
        return

    if (
        presenter.session_manager
        and len(presenter.session_manager.list_sessions()) == 1
    ):
        # Replace the only tab with the picker in one atomic store change, so
        # the tab strip never holds both tabs for an intermediate frame.
        try:
            presenter.main_controller.workspace.replace_workspace_session(
                INITIAL_WORKSPACE_SESSION_TYPE,
                closing_session_id=session_id,
            )
        except Exception:
            logger.exception(
                "on_workspace_tab_close_requested: failed to create session_picker"
            )
        return
    presenter.main_controller.workspace.close_workspace_session(session_id)
