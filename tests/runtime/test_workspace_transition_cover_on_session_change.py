"""Cover on active-session change (not only workspace tab strip clicks)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from ui.presenters.main_window.workspace import cover_active_session_transition


def _presenter_for(session, *, tab_hint):
    mask = MagicMock()
    window = SimpleNamespace(_workspace_transition_mask=mask)
    tab = SimpleNamespace(transition_hint=lambda: tab_hint)
    manager = SimpleNamespace(
        get_active_session=lambda: session,
        list_sessions=lambda: (session,),
    )
    presenter = SimpleNamespace(
        _last_covered_session_id=None,
        session_manager=manager,
        ui=SimpleNamespace(
            main_window=window,
            workspace_stack=object(),
            _tab_registry=SimpleNamespace(get_tab=lambda _t: tab),
        ),
        main_window_app=window,
    )
    return presenter, mask


def test_cover_active_session_transition_covers_new_session():
    session = SimpleNamespace(id="s1", session_type="image_compare")
    hint = SimpleNamespace(
        cover_on_enter=True,
        min_duration_ms=50,
        max_duration_ms=400,
    )
    presenter, mask = _presenter_for(session, tab_hint=hint)

    cover_active_session_transition(presenter)

    mask.cover.assert_called_once()
    assert mask.cover.call_args.kwargs["session_type"] == "image_compare"
    assert presenter._last_covered_session_id == "s1"

    cover_active_session_transition(presenter)
    assert mask.cover.call_count == 1


def test_cover_active_session_transition_respects_cover_on_enter_false():
    session = SimpleNamespace(id="s2", session_type="session_picker")
    hint = SimpleNamespace(
        cover_on_enter=False,
        min_duration_ms=50,
        max_duration_ms=300,
    )
    presenter, mask = _presenter_for(session, tab_hint=hint)

    cover_active_session_transition(presenter)

    mask.cover.assert_not_called()
    assert presenter._last_covered_session_id == "s2"
