

import logging
import threading
from typing import Callable, Optional, List
from PyQt6.QtCore import QObject, pyqtSignal

from .actions import Action
from .reducers import RootReducer

logger = logging.getLogger("ImproveImgSLI")

class Dispatcher(QObject):

    state_changed = pyqtSignal(str)

    def __init__(self, store):
        super().__init__()
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

                    old_viewport_plugin_state = getattr(self._store.viewport, '_viewport_plugin_state', None)
                    old_analysis_plugin_state = getattr(self._store.viewport, '_analysis_plugin_state', None)

                    old_viewport = self._store.viewport
                    self._store.viewport = new_store.viewport
                    self._store.document = new_store.document
                    self._store.settings = new_store.settings

                    if old_viewport_plugin_state:
                        self._store.viewport._viewport_plugin_state = old_viewport_plugin_state

                        view_state = self._store.viewport.view_state
                        for attr in ['split_position', 'split_position_visual', 'is_horizontal',
                                    'use_magnifier', 'magnifiers', 'active_magnifier_id',
                                    'magnifier_size_relative', 'capture_size_relative',
                                    'capture_position_relative', 'freeze_magnifier',
                                    'frozen_capture_point_relative', 'magnifier_offset_relative',
                                    'magnifier_spacing_relative', 'magnifier_offset_relative_visual',
                                    'magnifier_spacing_relative_visual', 'magnifier_is_horizontal',
                                    'magnifier_visible_left', 'magnifier_visible_center',
                                    'magnifier_visible_right', 'magnifier_internal_split',
                                    'magnifier_screen_center', 'magnifier_screen_size',
                                    'is_magnifier_combined', 'optimize_magnifier_movement',
                                    'pixmap_width', 'pixmap_height', 'image_display_rect_on_label',
                                    'fixed_label_width', 'fixed_label_height', 'resize_in_progress',
                                    'is_interactive_mode', 'is_dragging_split_line',
                                    'is_dragging_capture_point', 'is_dragging_split_in_magnifier',
                                    'is_dragging_any_slider', 'pressed_keys', 'space_bar_pressed',
                                    'showing_single_image_mode', 'movement_speed_per_sec',
                                    'text_bg_visual_height', 'text_bg_visual_width',
                                    'loaded_geometry', 'loaded_was_maximized',
                                    'loaded_previous_geometry', 'loaded_debug_mode_enabled']:
                            if hasattr(view_state, attr) and hasattr(old_viewport_plugin_state, attr):
                                setattr(old_viewport_plugin_state, attr, getattr(view_state, attr))

                    if old_analysis_plugin_state:
                        self._store.viewport._analysis_plugin_state = old_analysis_plugin_state

                        view_state = self._store.viewport.view_state
                        for attr in ['diff_mode', 'channel_view_mode']:
                            if hasattr(view_state, attr) and hasattr(old_analysis_plugin_state, attr):
                                setattr(old_analysis_plugin_state, attr, getattr(view_state, attr))

                    self._action_history.append(action)
                    if len(self._action_history) > self._max_history_size:
                        self._action_history.pop(0)

                    for subscriber in self._subscribers:
                        try:
                            subscriber(action)
                        except Exception as e:
                            logger.error(f"Error in dispatcher subscriber: {e}", exc_info=True)

                    self.state_changed.emit(scope)

            except Exception as e:
                logger.error(f"Error dispatching action {action.type.value}: {e}", exc_info=True)
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

