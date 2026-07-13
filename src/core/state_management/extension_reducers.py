from __future__ import annotations

from typing import Callable

from core.state_management.action_base import Action
from core.store import RenderConfig, SessionData

SessionDataReducerFn = Callable[[SessionData, Action], SessionData]
RenderConfigReducerFn = Callable[[RenderConfig, Action], RenderConfig]

# Each entry owns a specific tab's ``session_type``. ``SessionData`` is a
# generic, opaque-to-core container (see ``core/store_viewport.py``) whose
# concrete ``image_state``/``render_cache`` shapes are tab-specific and may
# be ``None`` for any other session type. Gating dispatch by session_type
# here means a reducer is simply never invoked for sessions it doesn't own,
# instead of relying on every reducer body to defensively check for ``None``.
_session_data_reducers: list[tuple[str, SessionDataReducerFn]] = []
_render_config_reducers: list[RenderConfigReducerFn] = []


def register_session_data_reducer(
    session_type: str, reducer: SessionDataReducerFn
) -> None:
    entry = (session_type, reducer)
    if entry not in _session_data_reducers:
        _session_data_reducers.append(entry)


def register_render_config_reducer(reducer: RenderConfigReducerFn) -> None:
    if reducer not in _render_config_reducers:
        _render_config_reducers.append(reducer)


def reduce_session_data_extensions(
    session_data: SessionData, action: Action, session_type: str | None = None
) -> SessionData:
    reduced = session_data
    for owner_session_type, reducer in tuple(_session_data_reducers):
        if owner_session_type != session_type:
            continue
        reduced = reducer(reduced, action)
    return reduced


def reduce_render_config_extensions(
    config: RenderConfig, action: Action
) -> RenderConfig:
    reduced = config
    for reducer in tuple(_render_config_reducers):
        reduced = reducer(reduced, action)
    return reduced


def clear_extension_reducers() -> None:
    _session_data_reducers.clear()
    _render_config_reducers.clear()
