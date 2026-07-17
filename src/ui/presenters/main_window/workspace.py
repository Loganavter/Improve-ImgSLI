from __future__ import annotations

import logging

from core.store import INITIAL_WORKSPACE_SESSION_TYPE

logger = logging.getLogger("ImproveImgSLI")


def initialize_workspace_state(presenter) -> None:
    presenter._file_dialog = None
    presenter._first_dialog_load_pending = True
    presenter._last_active_session_id = None


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


def on_workspace_tab_changed(presenter, index: int):
    if index < 0:
        return
    session_id = presenter.ui.workspace_tabs.tabData(index)
    if not (session_id and presenter.main_controller):
        return

    _cover_transition_for_session(presenter, session_id)
    presenter.main_controller.workspace.switch_workspace_session(session_id)


def _cover_transition_for_session(presenter, session_id: str) -> None:
    main_window = getattr(presenter.ui, "main_window", None)
    mask = getattr(main_window, "_workspace_transition_mask", None)
    if mask is None:
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
        return

    mask.cover(
        getattr(presenter.ui, "workspace_stack", None),
        min_duration_ms=hint.min_duration_ms,
        max_duration_ms=hint.max_duration_ms,
        session_type=session_type,
    )


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
