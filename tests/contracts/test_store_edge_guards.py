"""Store edge guards — undo/redo emit discipline, settings identity,
render-config gating/fail-loud, TRANSACTION accounting, no-op drops."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.state_management import slot_reducers as _slot_reducers_module
from core.state_management.actions import Action
from core.state_management.dispatcher import Dispatcher, _UNDOABLE_TYPES
from core.state_management.slot_reducers import register_state_slot_reducer


@pytest.fixture(autouse=True)
def _document_slot_reducer():
    saved = dict(_slot_reducers_module._SLOT_REDUCERS)
    register_state_slot_reducer("document", lambda state, action: state)
    yield
    _slot_reducers_module._SLOT_REDUCERS.clear()
    _slot_reducers_module._SLOT_REDUCERS.update(saved)


class _Session:
    def __init__(self, session_id: str):
        self.id = session_id
        self.state_slots: dict = {}


class _Store:
    """Minimal store double: real emit hook, controllable ADHD."""

    def __init__(self, sessions, active_id: str):
        self._sessions = sessions
        self.workspace = SimpleNamespace(active_session_id=active_id)
        self.settings = SimpleNamespace(current_language="en")
        self.viewport = SimpleNamespace(
            tag="initial",
            session_data=SimpleNamespace(
                render_cache=SimpleNamespace(unification_in_progress=False)
            ),
        )
        self.document = SimpleNamespace(seq=0)
        self.events: list[str] = []
        self.on_emit = None

    def get_workspace_session(self, session_id):
        return self._sessions.get(session_id)

    def get_active_workspace_session(self):
        return self._sessions.get(self.workspace.active_session_id)

    def get_session_state_slot(self, slot, *, session_id=None, default=None):
        if slot == "document":
            return self.document
        sess = (
            self._sessions[session_id]
            if session_id is not None
            else self.get_active_workspace_session()
        )
        return sess.state_slots.get(slot, default)

    def set_session_state_slot(self, slot, value, *, session_id=None, emit_scope=""):
        if slot == "document":
            self.document = value
            return
        sess = (
            self._sessions[session_id]
            if session_id is not None
            else self.get_active_workspace_session()
        )
        sess.state_slots[slot] = value

    def emit_state_change(self, scope):
        self.events.append(scope)
        if self.on_emit is not None:
            self.on_emit(scope)


class _Reducer:
    """Immutable-style stand-in: undoable actions (and TRANSACTION batches
    containing them) yield a fresh store; everything else is a no-op."""

    def __init__(self):
        self._counter = 0

    def _fresh(self, store, action):
        self._counter += 1
        n = self._counter
        document = SimpleNamespace(seq=n)
        viewport = SimpleNamespace(
            tag=f"{action.type}#{n}",
            session_data=store.viewport.session_data,
        )
        return SimpleNamespace(
            viewport=viewport,
            document=document,
            settings=store.settings,
            get_session_state_slot=lambda slot, doc=document: (
                doc if slot == "document" else None
            ),
        )

    def reduce(self, store, action: Action):
        if action.type == "TRANSACTION":
            inner = getattr(action, "actions", None) or []
            if any(a.type in _UNDOABLE_TYPES for a in inner):
                return self._fresh(store, action)
            return store
        if action.type not in _UNDOABLE_TYPES:
            return store
        return self._fresh(store, action)


def _mk_dispatcher():
    sessions = {"a": _Session("a"), "b": _Session("b")}
    store = _Store(sessions, "a")
    dispatcher = Dispatcher(store)
    dispatcher._reducer = _Reducer()
    return store, dispatcher


def _action(action_type: str) -> Action:
    from core.state_management.actions import (
        SetPressedKeysAction,
        SetSplitPositionAction,
        ToggleOrientationAction,
    )

    if action_type == "SET_SPLIT_POSITION":
        return SetSplitPositionAction(0.5)
    if action_type == "TOGGLE_ORIENTATION":
        return ToggleOrientationAction(is_horizontal=True)
    return SetPressedKeysAction([])


def _transaction(*inner_types: str) -> Action:
    from core.state_management.transaction import TransactionAction

    return TransactionAction([_action(t) for t in inner_types])


def test_undo_emits_outside_lock_reentrant_dispatch():
    """An on-emit subscriber that dispatches must not deadlock (reentrancy)."""
    store, dispatcher = _mk_dispatcher()
    dispatcher.dispatch(_action("SET_SPLIT_POSITION"))
    assert dispatcher.can_undo()

    lock_seen: list[bool] = []
    redispatched: list[str] = []

    def _on_emit(scope):
        # Would deadlock if undo still held the (non-reentrant) lock: both
        # can_undo and dispatch acquire it. Single-shot: unhook first so the
        # nested dispatch's own emit does not recurse.
        store.on_emit = None
        lock_seen.append(dispatcher._lock.locked())
        dispatcher.dispatch(_action("SET_SPLIT_POSITION"), scope="viewport")
        redispatched.append(scope)

    store.on_emit = _on_emit
    dispatcher.undo()
    assert lock_seen and all(seen is False for seen in lock_seen)
    assert redispatched
    assert store.events[0] == "viewport"


def test_redo_emits_outside_lock_reentrant_dispatch():
    store, dispatcher = _mk_dispatcher()
    dispatcher.dispatch(_action("SET_SPLIT_POSITION"))
    dispatcher.undo()
    assert dispatcher.can_redo()

    lock_seen: list[bool] = []

    def _on_emit(scope):
        lock_seen.append(dispatcher._lock.locked())

    store.on_emit = _on_emit
    dispatcher.redo()
    assert lock_seen and all(seen is False for seen in lock_seen)


def test_undo_redo_emit_viewport_plus_slots_and_nothing_when_empty():
    store, dispatcher = _mk_dispatcher()
    dispatcher.undo()
    dispatcher.redo()
    assert store.events == []

    dispatcher.dispatch(_action("SET_SPLIT_POSITION"))
    store.events.clear()
    dispatcher.undo()
    assert store.events[0] == "viewport"
    assert "document" in store.events
    store.events.clear()
    dispatcher.redo()
    assert store.events[0] == "viewport"
    assert "document" in store.events


def _settings_state(**overrides):
    from core.store_settings import SettingsState

    base = dict(
        current_language="en",
        ui_mode="beginner",
        auto_crop_black_borders=True,
        theme="auto",
        ui_font_mode="builtin",
        ui_font_family="",
        ui_scale_factor=1.0,
        debug_mode_enabled=False,
        system_notifications_enabled=True,
        video_recording_fps=60,
        window_was_maximized=False,
        window_x=0,
        window_y=0,
        window_width=800,
        window_height=600,
        export_favorite_dir=None,
        keyboard_overrides={},
    )
    base.update(overrides)
    return SettingsState(**base)


def _equal_settings_actions():
    from core.state_management import settings_actions as sa

    return [
        sa.SetLanguageAction("en"),
        sa.SetUIModeAction("beginner"),
        sa.SetAutoCropBlackBordersAction(True),
        sa.SetThemeAction("auto"),
        sa.SetUIFontModeAction("builtin"),
        sa.SetUIFontFamilyAction(""),
        sa.SetUIScaleFactorAction(1.0),
        sa.SetDebugModeEnabledAction(False),
        sa.SetSystemNotificationsEnabledAction(True),
        sa.SetVideoRecordingFpsAction(60),
        sa.SetWindowWasMaximizedAction(False),
        sa.SetWindowGeometryAction(0, 0, 800, 600),
        sa.SetExportFavoriteDirAction(None),
        sa.SetKeyboardOverridesAction({}),
    ]


def test_settings_reducer_identity_on_equal_values():
    """Every branch returns the identical object for an equal value."""
    from core.state_management.reducers import SettingsReducer

    settings = _settings_state()
    for action in _equal_settings_actions():
        assert SettingsReducer.reduce(settings, action) is settings, action.type


def test_settings_reducer_replaces_on_changed_values():
    from core.state_management import settings_actions as sa
    from core.state_management.reducers import SettingsReducer

    settings = _settings_state()
    assert SettingsReducer.reduce(settings, sa.SetLanguageAction("ru")).current_language == "ru"
    assert SettingsReducer.reduce(settings, sa.SetThemeAction("dark")).theme == "dark"
    geom = SettingsReducer.reduce(settings, sa.SetWindowGeometryAction(1, 2, 3, 4))
    assert (geom.window_x, geom.window_y, geom.window_width, geom.window_height) == (1, 2, 3, 4)
    assert geom is not settings
    overrides = SettingsReducer.reduce(
        settings, sa.SetKeyboardOverridesAction({"a.b": "Ctrl+S"})
    )
    assert overrides.keyboard_overrides == {"a.b": "Ctrl+S"}
    # Unknown action type: identity, no crash.
    assert SettingsReducer.reduce(settings, _action("SET_SPLIT_POSITION")) is settings


def test_render_config_fail_loud_on_wrong_type():
    from core.state_management import extension_reducers as ext
    from core.store import RenderConfig

    saved = list(ext._render_config_reducers)
    ext._render_config_reducers.clear()
    try:
        ext.register_render_config_reducer(lambda config, action: "not-a-config")
        with pytest.raises(TypeError, match="expected RenderConfig"):
            ext.reduce_render_config_extensions(RenderConfig(), _action("SET_SPLIT_POSITION"))
    finally:
        ext._render_config_reducers.clear()
        ext._render_config_reducers.extend(saved)


def test_render_config_session_gating():
    from core.state_management import extension_reducers as ext
    from core.store import RenderConfig

    saved = list(ext._render_config_reducers)
    ext._render_config_reducers.clear()
    try:
        calls: list[str] = []
        ext.register_render_config_reducer(
            lambda config, action: calls.append("owned") or config,
            session_type="tab_a",
        )
        ext.register_render_config_reducer(
            lambda config, action: calls.append("legacy") or config
        )
        config = RenderConfig()
        ext.reduce_render_config_extensions(
            config, _action("SET_SPLIT_POSITION"), session_type="tab_b"
        )
        assert calls == ["legacy"]
        calls.clear()
        ext.reduce_render_config_extensions(
            config, _action("SET_SPLIT_POSITION"), session_type="tab_a"
        )
        assert sorted(calls) == ["legacy", "owned"]
    finally:
        ext._render_config_reducers.clear()
        ext._render_config_reducers.extend(saved)


def test_transaction_commits_atomically_outside_undo_single_emit():
    """TRANSACTION: one history entry, one emit, no undo entry (documented)."""
    store, dispatcher = _mk_dispatcher()
    dispatcher.dispatch(
        _transaction("SET_SPLIT_POSITION", "TOGGLE_ORIENTATION"), scope="viewport"
    )
    assert store.events == ["viewport"]
    assert not dispatcher.can_undo()
    assert len(dispatcher.get_action_history()) == 1

    # A batch with no undoable inner action is a full no-op: no emit at all.
    store.events.clear()
    dispatcher.dispatch(_transaction("SET_PRESSED_KEYS"), scope="viewport")
    assert store.events == []
