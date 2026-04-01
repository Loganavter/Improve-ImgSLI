import logging
import threading
from dataclasses import fields, is_dataclass
from typing import Callable, List

from .actions import Action
from .reducers import RootReducer

logger = logging.getLogger("ImproveImgSLI")

def _sync_dataclass_fields(source, target) -> None:
    if source is None or target is None or not is_dataclass(target):
        return
    for field_info in fields(target):
        name = field_info.name
        if hasattr(source, name):
            setattr(target, name, getattr(source, name))

def _sync_plugin_states(viewport) -> None:
    viewport_plugin_state = getattr(viewport, "_viewport_plugin_state", None)
    analysis_plugin_state = getattr(viewport, "_analysis_plugin_state", None)

    if viewport_plugin_state is not None:
        _sync_dataclass_fields(viewport, viewport_plugin_state)

    if analysis_plugin_state is not None:
        _sync_dataclass_fields(viewport.view_state, analysis_plugin_state)

class Dispatcher:

    def __init__(self, store):
        self._store = store
        self._reducer = RootReducer()
        self._lock = threading.Lock()
        self._subscribers: List[Callable[[Action], None]] = []
        self._action_history: List[Action] = []
        self._max_history_size = 100

    @property
    def store(self):
        return self._store

    def dispatch(self, action: Action, scope: str = "viewport") -> None:
        with self._lock:
            try:

                new_store = self._reducer.reduce(self._store, action)

                if new_store is not self._store:

                    old_viewport_plugin_state = getattr(
                        self._store.viewport, "_viewport_plugin_state", None
                    )
                    old_analysis_plugin_state = getattr(
                        self._store.viewport, "_analysis_plugin_state", None
                    )

                    old_viewport = self._store.viewport
                    self._store.viewport = new_store.viewport
                    self._store.document = new_store.document
                    self._store.settings = new_store.settings

                    if old_viewport_plugin_state:
                        self._store.viewport._viewport_plugin_state = (
                            old_viewport_plugin_state
                        )

                    if old_analysis_plugin_state:
                        self._store.viewport._analysis_plugin_state = (
                            old_analysis_plugin_state
                        )

                    _sync_plugin_states(self._store.viewport)

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
                    f"Error dispatching action {action.type.value}: {e}", exc_info=True
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
