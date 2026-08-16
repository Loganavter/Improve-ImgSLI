import logging
import threading
import time
from typing import Callable, List

from .actions import Action
from .reducers import RootReducer

logger = logging.getLogger("ImproveImgSLI")

_ACTION_HISTORY_SLOT = "action_history"
_UNDO_STACK_SLOT = "undo_stack"
_REDO_STACK_SLOT = "redo_stack"

# Action types a user would expect Ctrl+Z to revert. Deliberately excludes:
# - global settings (theme/language/UI/font/export dirs — store-global, not
#   per-session);
# - transient interaction/visual state (drag scrubbers, pressed keys,
#   dragging flags, geometry derived from widget resize);
# - caches/metrics/in-progress flags (cached diff, PSNR/SSIM values,
#   unification-in-progress, cache invalidation);
# - pixel-bearing document actions (SET_ORIGINAL_IMAGE / SET_FULL_RES_IMAGE /
#   SET_PREVIEW_IMAGE / CLEAR_IMAGE_SLOT_DATA): loading.py closes the replaced
#   TiledPixelStore, so a reference-snapshot of the old document would hold a
#   closed store. Undo of image *browsing* is covered by SET_CURRENT_INDEX
#   (the host tab re-loads the entry on the "document" scope emit that
#   undo/redo produces — path+reload, since the snapshot's pixels may
#   reference the closed store).
_UNDOABLE_TYPES = frozenset(
    {
        "SET_SPLIT_POSITION",
        "TOGGLE_ORIENTATION",
        "SET_MOVEMENT_SPEED",
        "SET_DIFF_MODE",
        "SET_CHANNEL_VIEW_MODE",
        "SET_SHOWING_SINGLE_IMAGE_MODE",
        "SET_DISPLAY_RESOLUTION_LIMIT",
        "SET_ZOOM_INTERPOLATION_METHOD",
        "SET_INTERPOLATION_METHOD",
        "SET_MOVEMENT_INTERPOLATION_METHOD",
        "SET_INCLUDE_FILE_NAMES_IN_SAVED",
        "SET_FONT_SIZE_PERCENT",
        "SET_FONT_WEIGHT",
        "SET_TEXT_ALPHA_PERCENT",
        "SET_FILE_NAME_COLOR",
        "SET_FILE_NAME_BG_COLOR",
        "SET_DRAW_TEXT_BACKGROUND",
        "SET_TEXT_PLACEMENT_MODE",
        "SET_MAX_NAME_LENGTH",
        "SET_CURRENT_INDEX",
        "SET_DIVIDER_VISIBLE",
        "SET_DIVIDER_COLOR",
        "SET_DIVIDER_THICKNESS",
        "SET_GUIDES_ENABLED",
        "SET_GUIDES_THICKNESS",
        "SET_GUIDES_COLOR",
        "SET_GUIDES_SMOOTHING_ENABLED",
        "SET_GUIDES_SMOOTHING_INTERPOLATION_METHOD",
        "SET_MAGNIFIER_SIZE_RELATIVE",
        "TOGGLE_MAGNIFIER",
        "SET_MAGNIFIER_VISIBILITY",
        "TOGGLE_MAGNIFIER_ORIENTATION",
        "TOGGLE_FREEZE_MAGNIFIER",
        "SET_MAGNIFIER_POSITION",
        "SET_MAGNIFIER_INTERNAL_SPLIT",
        "UPDATE_MAGNIFIER_COMBINED_STATE",
        "SET_MAGNIFIER_OFFSET_RELATIVE",
        "SET_MAGNIFIER_SPACING_RELATIVE",
        "SET_OPTIMIZE_MAGNIFIER_MOVEMENT",
        "SET_MAGNIFIER_LASER_ENABLED",
        "SET_MAGNIFIER_MOVEMENT_INTERPOLATION_METHOD",
        "SET_MAGNIFIER_SCREEN_CENTER",
        "SET_MAGNIFIER_SCREEN_SIZE",
        "SET_CAPTURE_SIZE_RELATIVE",
        "SET_CAPTURE_VISIBLE",
        "SET_CAPTURE_COLOR",
        # multi_compare session state (slot "multi_compare.state"). Store
        # closing for removed slots is deferred (GC/session teardown), so a
        # reference-snapshot undo of add/remove restores a still-open store.
        "multi_compare/add_slot",
        "multi_compare/remove_slot",
        "multi_compare/rename_slot",
        "multi_compare/swap_slots",
        "multi_compare/move_slot",
        "multi_compare/set_split_weights",
        "multi_compare/set_label_settings",
        "multi_compare/set_divider_settings",
        "multi_compare/set_zoom",
        "multi_compare/set_pan",
        "multi_compare/reset_view",
        "multi_compare/apply_layout_tree",
    }
)

# Continuous-gesture action types: a single drag/scroll dispatches many of
# these. Coalesce consecutive same-type dispatches so one undo step returns
# to the pre-gesture state instead of stepping through every intermediate.
_COALESCE_TYPES = frozenset(
    {
        "SET_SPLIT_POSITION",
        "SET_MAGNIFIER_POSITION",
        "SET_MAGNIFIER_OFFSET_RELATIVE",
        "SET_MAGNIFIER_SPACING_RELATIVE",
        "SET_CAPTURE_SIZE_RELATIVE",
        "SET_MOVEMENT_SPEED",
        "multi_compare/set_zoom",
        "multi_compare/set_pan",
        "multi_compare/set_split_weights",
    }
)

# Non-continuous action types are grouped the same way (one undo step for a
# burst) when the *same type* is dispatched again within this window — a
# quick click-click on one control is one user intent, two clicks ten seconds
# apart are two. Matches the platform double-click interval convention.
_RAPID_ACTION_GROUP_MS = 400


class Dispatcher:

    def __init__(self, store):
        self._store = store
        self._reducer = RootReducer()
        self._lock = threading.Lock()
        self._subscribers: List[Callable[[Action], None]] = []
        self._action_history: List[Action] = []
        self._undo_stack: List[tuple] = []
        self._redo_stack: List[tuple] = []
        self._bound_session_id: str | None = None
        self._max_history_size = 100
        # Monotonic timestamp of the last undoable dispatch per action type —
        # drives the rapid-same-type grouping window.
        self._last_dispatch_ts: dict[str, float] = {}
        self._bind_history_to_active_session()

    def bind_history_for_session(self, session_id: str) -> None:
        """Point undo history (action list + undo/redo stacks) at ``session_id``'s slots."""
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

            def _bind(slot: str):
                stack = session.state_slots.get(slot)
                if stack is None:
                    stack = []
                    session.state_slots[slot] = stack
                return stack

            self._action_history = _bind(_ACTION_HISTORY_SLOT)
            self._undo_stack = _bind(_UNDO_STACK_SLOT)
            self._redo_stack = _bind(_REDO_STACK_SLOT)
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

                from .slot_reducers import iter_state_slot_reducers

                slot_reducers = tuple(iter_state_slot_reducers())

                # Reference-snapshot for undo/redo: reducers return fresh
                # immutable state objects, so the pre-dispatch refs stay
                # untouched and are a cheap, safe undo snapshot (no deep copy
                # of pixel stores).
                old_viewport = self._store.viewport
                old_slots = {
                    name: self._store.get_session_state_slot(name)
                    for name, _ in slot_reducers
                }

                new_store = self._reducer.reduce(self._store, action)

                if new_store is not self._store:

                    self._store.viewport = new_store.viewport
                    self._store.settings = new_store.settings

                    # The active workspace session owns the state slots and
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

                    # Sync every slot-reducer slot back to the live store and
                    # the active session (only the changed ones).
                    new_slots: dict = {}
                    for name, _ in slot_reducers:
                        new_value = new_store.get_session_state_slot(name)
                        new_slots[name] = new_value
                        if new_value is not old_slots.get(name):
                            self._store.set_session_state_slot(
                                name, new_value, emit_scope=""
                            )
                            if active_session is not None:
                                active_session.state_slots[name] = new_value
                    if active_session is not None:
                        active_session.viewport = self._store.viewport

                    self._action_history.append(action)
                    if len(self._action_history) > self._max_history_size:
                        self._action_history.pop(0)

                    if action.type in _UNDOABLE_TYPES:
                        after = (new_store.viewport, new_slots)
                        before = (old_viewport, old_slots)
                        now = time.monotonic()
                        last_ts = self._last_dispatch_ts.get(action.type)
                        self._last_dispatch_ts[action.type] = now
                        rapid_burst = (
                            last_ts is not None
                            and (now - last_ts) * 1000.0 < _RAPID_ACTION_GROUP_MS
                        )
                        if (
                            not self._redo_stack
                            and self._undo_stack
                            and self._undo_stack[-1][0] == action.type
                            and (
                                action.type in _COALESCE_TYPES or rapid_burst
                            )
                        ):
                            # Continuous gesture or a rapid same-type burst:
                            # move the undo "after" forward so one undo step
                            # returns to the pre-gesture/pre-burst state.
                            self._undo_stack[-1] = (
                                action.type,
                                self._undo_stack[-1][1],
                                after,
                            )
                        else:
                            self._undo_stack.append((action.type, before, after))
                        if len(self._undo_stack) > self._max_history_size:
                            self._undo_stack.pop(0)
                        self._redo_stack.clear()

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
            self._undo_stack.clear()
            self._redo_stack.clear()
            self._last_dispatch_ts.clear()

    # --- Undo / redo -----------------------------------------------------

    def _busy_loading(self) -> bool:
        """Undo is blocked while an image is loading/unifying (matches the
        video editor's policy of disabling undo during a load)."""
        try:
            render_cache = self._store.viewport.session_data.render_cache
            return bool(getattr(render_cache, "unification_in_progress", False))
        except Exception:
            return False

    def can_undo(self) -> bool:
        with self._lock:
            return bool(self._undo_stack) and not self._busy_loading()

    def can_redo(self) -> bool:
        with self._lock:
            return bool(self._redo_stack) and not self._busy_loading()

    def undo(self) -> None:
        with self._lock:
            if self._busy_loading() or not self._undo_stack:
                return
            entry = self._undo_stack.pop()
            self._redo_stack.append(entry)
            _type, before, _after = entry
            viewport, slots = before
            self._restore_session_state(viewport, slots)
            self._store.emit_state_change("viewport")
            # The restored snapshot covers every registered slot — notify the
            # consumers that those scopes changed too (tabs use e.g. the
            # "document" scope to re-sync state that the reference snapshot
            # cannot carry, like a closed pixel store).
            for name in slots:
                self._store.emit_state_change(name)

    def redo(self) -> None:
        with self._lock:
            if self._busy_loading() or not self._redo_stack:
                return
            entry = self._redo_stack.pop()
            self._undo_stack.append(entry)
            _type, _before, after = entry
            viewport, slots = after
            self._restore_session_state(viewport, slots)
            self._store.emit_state_change("viewport")
            for name in slots:
                self._store.emit_state_change(name)

    def _restore_session_state(self, viewport, slots) -> None:
        """Re-point the active session at a snapshot (mirrors dispatch's
        write-back, minus a reducer run and minus history recording).

        ``slots`` maps every registered slot-reducer name to its snapshot
        value; each is written back and re-pointed on the active session.
        """
        self._store.viewport = viewport
        active_session = None
        get_active = getattr(self._store, "get_active_workspace_session", None)
        if callable(get_active):
            try:
                active_session = get_active()
            except Exception:
                active_session = None
        for name, value in slots.items():
            self._store.set_session_state_slot(name, value, emit_scope="")
            if active_session is not None:
                active_session.state_slots[name] = value
        if active_session is not None:
            active_session.viewport = viewport