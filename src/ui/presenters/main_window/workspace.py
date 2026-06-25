from __future__ import annotations

import logging

from plugins.video_editor.model import VideoSessionModel
from resources.translations import tr

logger = logging.getLogger("ImproveImgSLI")

_SESSION_TITLE_KEYS = {
    "image_compare": "workspace.session_types.image_compare",
    "video_compare": "workspace.session_types.video_compare",
    "multi_compare": "workspace.session_types.multi_compare",
}


def initialize_workspace_state(presenter) -> None:
    presenter._file_dialog = None
    presenter._first_dialog_load_pending = True
    presenter._video_session_model: VideoSessionModel | None = None
    presenter._last_active_session_id = None

def configure_workspace_actions(presenter):
    actions = []
    logger.debug(
        "configure_workspace_actions: main_controller=%s session_manager=%s",
        presenter.main_controller,
        getattr(presenter.main_controller, "session_manager", None) if presenter.main_controller else None,
    )
    if presenter.main_controller:
        try:
            blueprints = list(presenter.main_controller.workspace.list_session_blueprints())
        except Exception:
            logger.exception("configure_workspace_actions: list_session_blueprints failed")
            blueprints = []
        logger.debug("configure_workspace_actions: blueprints raw=%s", blueprints)
        language = presenter.store.settings.current_language
        for blueprint in blueprints:
            fallback = blueprint.resolved_title() or blueprint.session_type
            key = _SESSION_TITLE_KEYS.get(blueprint.session_type)
            label = tr(key, language) if key is not None else fallback
            if label == key:
                label = fallback
            actions.append((label, blueprint.session_type))
    btn = presenter.ui.btn_new_session
    logger.debug(
        "configure_workspace_actions: actions=%s btn=%s visible=%s enabled=%s",
        actions, btn, btn.isVisible(), btn.isEnabled(),
    )
    btn.set_actions([])
    logger.debug(
        "configure_workspace_actions: after set_actions _has_menu=%s capabilities=%s",
        getattr(btn, "_has_menu", "<missing>"),
        [type(c).__name__ for c in getattr(btn, "_capabilities", [])],
    )

    try:
        btn.clicked.disconnect(_log_new_session_clicked)
    except (TypeError, RuntimeError):
        pass
    btn.clicked.connect(_log_new_session_clicked)


def _log_new_session_clicked():
    logger.debug("btn_new_session.clicked emitted")

def on_new_workspace_tab_requested(presenter):
    if not presenter.main_controller:
        return
    try:
        presenter.main_controller.workspace.create_workspace_session(
            "session_picker",
            activate=True,
        )
    except Exception:
        logger.exception("on_new_workspace_tab_requested: create session_picker failed")

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
    session_type = active.session_type if active else "image_compare"
    session_title = active.title if active else None
    presenter.ui.sync_session_mode(session_type, session_title)
    sync_video_session_view(presenter)

def sync_video_session_view(presenter):
    if not presenter.session_manager:
        return
    active = presenter.session_manager.get_active_session()
    if active is None or active.session_type != "video_compare":
        presenter._video_session_model = None
        presenter.ui.video_session_widget.clear()
        return

    if (
        presenter._video_session_model is None
        or presenter._video_session_model.session_id != active.id
    ):
        presenter._video_session_model = VideoSessionModel(
            store=presenter.store,
            session_manager=presenter.session_manager,
            main_controller=presenter.main_controller,
            session_id=active.id,
        )

    presenter.ui.video_session_widget.set_snapshot(
        presenter._video_session_model.get_snapshot()
    )

def on_workspace_tab_changed(presenter, index: int):
    if index < 0:
        return
    session_id = presenter.ui.workspace_tabs.tabData(index)
    if session_id and presenter.main_controller:
        presenter.main_controller.workspace.switch_workspace_session(session_id)


def on_workspace_tab_close_requested(presenter, index: int):
    if index < 0:
        return
    session_id = presenter.ui.workspace_tabs.tabData(index)
    if not session_id or not presenter.main_controller:
        return
    # Closing the last remaining session opens a session-picker session first
    # so the user can pick a new tab type instead of the app shutting down.
    if (
        presenter.session_manager
        and len(presenter.session_manager.list_sessions()) == 1
    ):
        try:
            presenter.main_controller.workspace.create_workspace_session(
                "session_picker", activate=True
            )
        except Exception:
            logger.exception("on_workspace_tab_close_requested: failed to create session_picker")
            return
    presenter.main_controller.workspace.close_workspace_session(session_id)

def on_workspace_session_triggered(presenter, action):
    logger.debug("on_workspace_session_triggered: action=%r type=%s", action, type(action).__name__)
    session_type = action.data() if hasattr(action, "data") and callable(action.data) else action
    logger.debug(
        "on_workspace_session_triggered: session_type=%s main_controller=%s",
        session_type, presenter.main_controller,
    )
    if not session_type or not presenter.main_controller:
        return
    try:
        session = presenter.main_controller.workspace.create_workspace_session(
            session_type, activate=True
        )
    except Exception:
        logger.exception("on_workspace_session_triggered: create_workspace_session failed")
        return
    logger.debug("on_workspace_session_triggered: created session=%s", session)

def on_video_session_advance_requested(presenter):
    if presenter._video_session_model is None:
        return
    presenter._video_session_model.advance_timeline()

def on_video_session_attach_resource_requested(presenter):
    if presenter._video_session_model is None:
        return
    presenter._video_session_model.attach_decoder()

def on_video_session_create_image_compare_requested(presenter):
    if presenter._video_session_model is None:
        return
    presenter._video_session_model.open_image_compare()
