from __future__ import annotations

from typing import Callable

from core.state_management.action_base import Action
from core.store import RenderConfig, SessionData

SessionDataReducerFn = Callable[[SessionData, Action], SessionData]
RenderConfigReducerFn = Callable[[RenderConfig, Action], RenderConfig]

_session_data_reducers: list[SessionDataReducerFn] = []
_render_config_reducers: list[RenderConfigReducerFn] = []


def register_session_data_reducer(reducer: SessionDataReducerFn) -> None:
    if reducer not in _session_data_reducers:
        _session_data_reducers.append(reducer)


def register_render_config_reducer(reducer: RenderConfigReducerFn) -> None:
    if reducer not in _render_config_reducers:
        _render_config_reducers.append(reducer)


def reduce_session_data_extensions(
    session_data: SessionData, action: Action
) -> SessionData:
    reduced = session_data
    for reducer in tuple(_session_data_reducers):
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

