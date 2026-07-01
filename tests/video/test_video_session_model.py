from __future__ import annotations

from types import SimpleNamespace

from core.session_blueprints import SessionBlueprint, SessionResourceBlueprint
from plugins.video_editor.model import VideoSessionModel


def test_open_image_compare_uses_comparison_resource_blueprint():
    video_session = SimpleNamespace(id="video-1", session_type="video_compare")
    created = {}

    store = SimpleNamespace(
        get_session_state_slot=lambda *_args, **_kwargs: {"position": 42},
    )
    session_manager = SimpleNamespace(get_active_session=lambda: video_session)
    workspace = SimpleNamespace(
        list_session_blueprints=lambda: (
            SessionBlueprint(session_type="other", plugin_name="other"),
            SessionBlueprint(
                session_type="pair_compare",
                plugin_name="comparison",
                resource_namespaces=(SessionResourceBlueprint("comparison"),),
            ),
        ),
        create_workspace_session=lambda session_type, **kwargs: created.update(
            session_type=session_type,
            kwargs=kwargs,
        )
        or SimpleNamespace(id="created", session_type=session_type),
    )
    model = VideoSessionModel(
        store=store,
        session_manager=session_manager,
        main_controller=SimpleNamespace(workspace=workspace),
    )

    result = model.open_image_compare()

    assert result.session_type == "pair_compare"
    assert created["session_type"] == "pair_compare"
    assert created["kwargs"]["activate"] is True
    assert created["kwargs"]["metadata"] == {
        "source_video_session_id": "video-1",
        "source_timeline_position": 42,
    }
