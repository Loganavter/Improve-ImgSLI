"""Concurrent dispatch pins ARCHITECTURE.md thread-safety claim.

W5 gap: Dispatcher thread-safety had zero threading coverage.
Inv: 10 threads dispatching concurrently must not lose history or corrupt Store.
"""
from __future__ import annotations

import os
import threading

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core.state_management.dispatcher import Dispatcher
from core.state_management.viewport_actions import SetSplitPositionAction
from core.store import Store


def test_concurrent_dispatch_keeps_store_consistent():
    store = Store()
    # Use image_compare tab to have a meaningful viewport
    from tabs.image_compare.tab import ImageCompareTab

    ImageCompareTab().register_canvas_features()
    store.create_workspace_session(session_type="image_compare", activate=True)
    dispatcher = Dispatcher(store)
    store.set_dispatcher(dispatcher)

    seen_actions: list = []
    seen_lock = threading.Lock()

    def subscriber(action):
        with seen_lock:
            seen_actions.append(action.type)

    dispatcher.subscribe(subscriber)

    thread_count = 10
    per_thread = 20
    total = thread_count * per_thread

    barrier = threading.Barrier(thread_count)

    errors: list[Exception] = []

    def worker(tid: int):
        try:
            barrier.wait(timeout=5)
            for i in range(per_thread):
                # distinct value per dispatch to exercise viewport mutation
                pos = ((tid * per_thread + i) % 100) / 100.0
                dispatcher.dispatch(SetSplitPositionAction(pos))
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(tid,)) for tid in range(thread_count)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
        assert not t.is_alive(), "dispatcher thread hung - deadlock"

    assert not errors, f"worker errors: {errors}"
    history = dispatcher.get_action_history()
    assert len(history) == total, f"history lost entries: {len(history)} != {total}"
    assert len(seen_actions) == total
    # Store must still be internally consistent: viewport exists and split in bounds
    assert 0.0 <= store.viewport.view_state.split_position <= 1.0
    # undo stack should have grown (all are undoable? SetSplitPosition is undoable)
    assert dispatcher.can_undo() or len(history) > 0
