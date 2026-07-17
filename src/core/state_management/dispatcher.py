import logging
import threading
from typing import Callable, List

from .actions import Action
from .reducers import RootReducer

logger = logging.getLogger("ImproveImgSLI")

_ACTION_HISTORY_SLOT = "action_history"


class Dispatcher:

    def __init__(self, store):
        self._store = store
        self._reducer = RootReducer()
        self._lock = threading.Lock()
        self._subscribers: List[Callable[[Action], None]] = []
        self._action_history: List[Action] = []
        self._bound_session_id: str | None = None
        self._max_history_size = 100
        self._bind_history_to_active_session()

    def bind_history_for_session(self, session_id: str) -> None:
        """Point undo history at ``session_id``'s ``action_history`` slot."""
        with self._lock:
            if self._bound_session_id == session_id:
                return
            store = self._store
            get_session = getattr(store, "get_workspace_session", None)
            if not callable(get_session):
                return
            session = get_session(session_id)
            if session is None:
                return
            history = session.state_slots.get(_ACTION_HISTORY_SLOT)
            if history is None:
                history = []
                session.state_slots[_ACTION_HISTORY_SLOT] = history
            self._action_history = history
            self._bound_session_id = session_id

    def _bind_history_to_active_session(self) -> None:
        get_active = getattr(self._store, "get_active_workspace_session", None)
        if not callable(get_active):
            return
        try:
            active = get_active()
        except Exception:
            return
        if active is not None:
            self.bind_history_for_session(active.id)

    @property
    def store(self):
        return self._store

    def dispatch(self, action: Action, scope: str = "viewport") -> None:
        with self._lock:
            try:

                new_store = self._reducer.reduce(self._store, action)

                if new_store is not self._store:

                    self._store.viewport = new_store.viewport
                    self._store.set_session_state_slot(
                        "document",
                        new_store.get_session_state_slot("document"),
                        emit_scope="",
                    )
                    self._store.settings = new_store.settings

                    # The active workspace session owns ``document`` and
                    # ``viewport``. Reducers return fresh instances, so the
                    # session's references must be re-pointed here — otherwise
                    # switching back to this session restores the pre-action
                    # state (lost image lists, lost view state, etc).
                    active_session = None
                    get_active = getattr(self._store, "get_active_workspace_session", None)
                    if callable(get_active):
                        try:
                            active_session = get_active()
                        except Exception:
                            active_session = None
                    if active_session is not None:
                        active_session.state_slots["document"] = (
                            self._store.get_session_state_slot("document")
                        )
                        active_session.viewport = self._store.viewport

                    self._action_history.append(action)
                    if len(self._action_history) > self._max_history_size:
                        self._action_history.pop(0)

                    for subscriber in self._subscribers:
                        try:
                            subscriber(action)
                        except Exception as e:
                            logger.error(
                                f"Error in dispatcher subscriber: {e}", exc_info=True
                            )

                    self._store.emit_state_change(scope)

            except Exception as e:
                logger.error(
                    f"Error dispatching action {action.type}: {e}", exc_info=True
                )
                raise

    def subscribe(self, callback: Callable[[Action], None]) -> None:
        if callback not in self._subscribers:
            self._subscribers.append(callback)

    def unsubscribe(self, callback: Callable[[Action], None]) -> None:
        if callback in self._subscribers:
            self._subscribers.remove(callback)

    def get_action_history(self) -> List[Action]:
        with self._lock:
            return self._action_history.copy()

    def clear_history(self) -> None:
        with self._lock:
            self._action_history.clear()
