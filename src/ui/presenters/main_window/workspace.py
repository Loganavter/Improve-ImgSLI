from __future__ import annotations

from plugins.video_editor.model import VideoSessionModel

def initialize_workspace_state(presenter) -> None:
    presenter._file_dialog = None
    presenter._first_dialog_load_pending = True
    presenter._video_session_model: VideoSessionModel | None = None

def configure_workspace_actions(presenter):
    actions = []
    if presenter.main_controller:
        for blueprint in presenter.main_controller.workspace.list_session_blueprints():
            label = blueprint.resolved_title() or blueprint.session_type
            actions.append((label, blueprint.session_type))
    presenter.ui.btn_new_session.set_actions(actions)

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

def on_workspace_session_triggered(presenter, action):
    session_type = action.data()
    if not session_type or not presenter.main_controller:
        return
    presenter.main_controller.workspace.create_workspace_session(
        session_type, activate=True
    )

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
