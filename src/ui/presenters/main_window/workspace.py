from __future__ import annotations

import logging

from core.store import INITIAL_WORKSPACE_SESSION_TYPE

logger = logging.getLogger("ImproveImgSLI")


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
    sessions = ()
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
        logger.debug("[workspace-transition] tab_changed ignored index=%s", index)
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

    logger.debug(
        "[workspace-transition] tab_changed index=%s session_id=%s",
        index,
        session_id,
    )
    # Cover runs from on_store_state_changed(workspace) so session-picker /
    # Find Action / create-session paths also get the flash (workspace tabs
    # strip is often hidden).
    presenter.main_controller.workspace.switch_workspace_session(session_id)


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
        logger.debug(
            "[workspace-transition] cover skipped: same session_id=%s",
            active.id,
        )
        return
    logger.debug(
        "[workspace-transition] active session change %r -> %r type=%r",
        last_id,
        active.id,
        getattr(active, "session_type", None),
    )
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
        logger.debug(
            "[workspace-transition] cover skipped: cover_on_enter=False "
            "(session_type=%r)",
            session_type,
        )
        return

    stack = getattr(presenter.ui, "workspace_stack", None)
    logger.debug(
        "[workspace-transition] requesting cover session_type=%r "
        "hint=(min=%s max=%s) mask_id=%s host=%r stack=%r",
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
            logger.debug(
                "[workspace-transition] mask resolved on %r id=%s",
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
                logger.debug(
                    "[workspace-transition] mask migrated from _app_host "
                    "to %r id=%s",
                    type(window).__name__,
                    id(mask),
                )
                return mask, window
    logger.debug(
        "[workspace-transition] mask resolve failed candidates=%s",
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
        try:
            presenter.main_controller.workspace.create_workspace_session(
                INITIAL_WORKSPACE_SESSION_TYPE, activate=True
            )
        except Exception:
            logger.exception(
                "on_workspace_tab_close_requested: failed to create session_picker"
            )
            return
    presenter.main_controller.workspace.close_workspace_session(session_id)
