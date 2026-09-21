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
# (owner_session_type | None, reducer). ``None`` = legacy ungated entry:
# invoked for every session (fail-open for reducers registered before
# session gating existed). Prefer registering with an explicit owner.
_render_config_reducers: list[tuple[str | None, RenderConfigReducerFn]] = []


def register_session_data_reducer(
    session_type: str, reducer: SessionDataReducerFn
) -> None:
    entry = (session_type, reducer)
    if entry not in _session_data_reducers:
        _session_data_reducers.append(entry)


def register_render_config_reducer(
    reducer: RenderConfigReducerFn, session_type: str | None = None
) -> None:
    entry = (session_type, reducer)
    if entry not in _render_config_reducers:
        _render_config_reducers.append(entry)


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
    config: RenderConfig, action: Action, session_type: str | None = None
) -> RenderConfig:
    """Run owned render-config reducers for ``session_type`` (fail-loud).

    Reducers registered with an explicit owner are skipped for other
    sessions; legacy owner-less entries still run everywhere. A reducer that
    returns anything but a ``RenderConfig`` raises ``TypeError`` immediately
    instead of poisoning the viewport with a wrong-typed config that would
    only explode screens away.
    """
    reduced = config
    for owner_session_type, reducer in tuple(_render_config_reducers):
        if owner_session_type is not None and owner_session_type != session_type:
            continue
        reduced = reducer(reduced, action)
        if not isinstance(reduced, RenderConfig):
            raise TypeError(
                f"render-config reducer {getattr(reducer, '__qualname__', reducer)!r} "
                f"returned {type(reduced).__name__}, expected RenderConfig"
            )
    return reduced

