"""Session replacement is one atomic store change.

The session-picker replace flow (create the new session + close the picker)
must emit a single store change, so workspace listeners — and the adaptive
tab strip — only ever see the post-replacement session list. Two separate
changes would make the strip hold both tabs for an intermediate frame.
"""

from __future__ import annotations

from types import SimpleNamespace

from core.main_controller_parts.sessions import WorkspaceSessionActions
from core.store import Store


def test_store_batch_defers_and_flushes_changes_once():
    store = Store()
    changes: list[str] = []
    observed: list[list[str]] = []
    store.on_change(lambda scope: changes.append(scope))
    store.on_change(
        lambda _scope: observed.append(
            [s.session_type for s in store.list_workspace_sessions()]
        )
    )
    picker_id = store.get_active_workspace_session().id

    with store.batch_changes():
        store.create_workspace_session(session_type="image_compare", activate=True)
        store.close_workspace_session(picker_id)

    # Flushed once per scope, in first-emitted order — no per-step emissions.
    assert changes == ["workspace", "document", "viewport"]
    # Every listener invocation saw the coherent final state (single
    # image_compare session), never the intermediate two-session list.
    assert observed and all(
        types == ["image_compare"] for types in observed
    )
    final = [s.session_type for s in store.list_workspace_sessions()]
    assert final == ["image_compare"]


def test_batch_flushes_even_when_inner_op_raises():
    store = Store()
    changes: list[str] = []
    store.on_change(lambda scope: changes.append(scope))
    picker_id = store.get_active_workspace_session().id

    class _Boom:
        def __enter__(self):
            raise RuntimeError("create failed")

    try:
        with store.batch_changes():
            store.create_workspace_session(session_type="image_compare", activate=True)
            store.close_workspace_session(picker_id)
            raise RuntimeError("boom")
    except RuntimeError:
        pass

    # The mutation that happened before the raise is still announced; the
    # batch must not swallow the flush on the exception path.
    assert changes == ["workspace", "document", "viewport"]


class _FakeSessionManager:
    def __init__(self, store: Store):
        self.store = store
        self.calls: list[tuple] = []

    def get_active_session(self):
        return self.store.get_active_workspace_session()

    def get_session(self, session_id):
        return self.store.get_workspace_session(session_id)

    def get_session_blueprint(self, session_type):
        from core.session_blueprints import SessionBlueprint

        return SessionBlueprint(session_type=session_type, plugin_name="test")

    def create_session(self, session_type, *, activate=True, title=None, metadata=None):
        self.calls.append(("create", session_type, activate))
        return self.store.create_workspace_session(
            title=title,
            session_type=session_type,
            activate=activate,
        )

    def switch_to_session(self, session_id):
        return self.store.switch_workspace_session(session_id)

    def close_session(self, session_id):
        self.calls.append(("close", session_id))
        return self.store.close_workspace_session(session_id)


def test_controller_replace_workspace_session_is_atomic():
    store = Store()
    changes: list[str] = []
    store.on_change(lambda scope: changes.append(scope))
    observed: list[int] = []
    store.on_change(
        lambda _scope: observed.append(len(store.list_workspace_sessions()))
    )
    picker_id = store.get_active_workspace_session().id

    events = []
    sm = _FakeSessionManager(store)
    controller = SimpleNamespace(
        session_manager=sm,
        event_bus=SimpleNamespace(emit=lambda e: events.append(type(e).__name__)),
    )
    actions = WorkspaceSessionActions(controller)

    session = actions.replace_workspace_session(
        "image_compare", closing_session_id=picker_id
    )

    assert session.session_type == "image_compare"
    assert sm.calls == [("create", "image_compare", True), ("close", picker_id)]
    # Single atomic flush — listeners never saw two sessions.
    assert observed == [1, 1, 1]
    assert changes == ["workspace", "document", "viewport"]
    assert [s.session_type for s in store.list_workspace_sessions()] == [
        "image_compare"
    ]
    # Per-op lifecycle events still fire for tab hooks.
    assert events == [
        "WorkspaceSessionCreatedEvent",
        "WorkspaceSessionActivatedEvent",
        "WorkspaceSessionClosedEvent",
    ]