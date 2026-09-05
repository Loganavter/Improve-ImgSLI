"""Phase A close-leaks: shared pyramid + save_flow sticky-toast terminals.

Covers ``tabs._shared`` only (root tests must not deep-import tab internals).
"""

import os
import threading
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class _FakeToastManager:
    def __init__(self):
        self._next_id = 100
        self.shown = []
        self.updated = []
        self.closed = []

    def show_toast(self, message, **kwargs):
        self._next_id += 1
        self.shown.append((self._next_id, message, kwargs))
        return self._next_id

    def update_toast(self, toast_id, message, **kwargs):
        self.updated.append((toast_id, message, kwargs))

    def close_toast(self, toast_id):
        self.closed.append(toast_id)


class _FakeToastCoordinator:
    """Minimal LoadingToastCoordinator stand-in (finish/dismiss/pop)."""

    def __init__(self):
        self.finished = []
        self.dismissed = []

    def finish(self, slot_id):
        self.finished.append(slot_id)

    def dismiss(self, slot_id):
        self.dismissed.append(slot_id)

    def bump_pyramid_started(self, slot_id):
        pass

    def set_progress(self, slot_id, percent):
        pass


def _make_pyramid(toast=None):
    from tabs._shared.pyramid import PyramidBuildCoordinator

    return PyramidBuildCoordinator(
        get_thread_pool=lambda: SimpleNamespace(start=lambda w: None),
        toast_coordinator=toast,
    )


def test_pyramid_already_in_flight_skip_finishes_toast():
    """Already-in-flight skip must still terminate the slot toast."""
    toast = _FakeToastCoordinator()
    coord = _make_pyramid(toast)
    store = SimpleNamespace(width=8, height=8)

    from shared.rendering.image_identity import image_uid

    uid = image_uid(store)
    coord._pyramid_builds.add(uid)

    assert coord.start_build(store, slot_id=7) is False
    assert toast.finished == [7]


def test_pyramid_build_finished_dismisses_stuck_mapping():
    """Abort/stalled finish (mapping still present) must close the toast."""
    toast = _FakeToastCoordinator()
    coord = _make_pyramid(toast)
    coord._pyramid_builds.add(4242)
    coord._pyramid_toast_slot[4242] = 9

    coord._on_build_finished(4242)

    assert 4242 not in coord._pyramid_toast_slot
    assert 4242 not in coord._pyramid_builds
    assert toast.dismissed == [9] or toast.finished == [9]


def _make_save_flow(toast_manager, *, sync_fallback=False):
    from tabs._shared.save_flow import SaveFlowCoordinator

    return SaveFlowCoordinator(
        get_thread_pool=lambda: None,
        get_toast_manager=lambda: toast_manager,
        tr_func=lambda key, default=None: default if default is not None else key,
        sync_fallback=sync_fallback,
    )


def test_save_done_on_external_cancel_updates_canceled_and_finalizes():
    mgr = _FakeToastManager()
    flow = _make_save_flow(mgr)
    cancel_event = threading.Event()
    cancel_event.set()
    flow._save_cancellation[55] = cancel_event

    flow._on_save_worker_done(55, cancel_event, "/tmp/out.png")

    assert 55 not in flow._save_cancellation
    assert mgr.updated
    toast_id, message, kwargs = mgr.updated[-1]
    assert toast_id == 55
    assert "Canceled" in message
    assert kwargs["success"] is False


def test_save_signal_connect_failure_routes_via_error_not_bare_finalize():
    mgr = _FakeToastManager()
    flow = _make_save_flow(mgr)

    def _raise(*_a, **_k):
        raise RuntimeError("boom-connect")

    worker = SimpleNamespace(
        kwargs={},
        signals=SimpleNamespace(
            progress=SimpleNamespace(connect=_raise),
            result=SimpleNamespace(connect=lambda *_a, **_k: None),
            error=SimpleNamespace(connect=lambda *_a, **_k: None),
        ),
    )
    options = {"output_dir": "/tmp", "file_name": "img", "format": "PNG"}
    flow.start_with_worker(options, lambda _ev: worker)

    # Error path must surface an error toast (not a silent finalize).
    assert mgr.updated
    _tid, message, kwargs = mgr.updated[-1]
    assert "Error saving" in message
    assert kwargs["success"] is False
    assert not flow._save_cancellation


def test_save_sync_cancel_swallow_updates_canceled_and_finalizes():
    from shared.image_processing.pil_save import SAVE_CANCELED_MESSAGE

    mgr = _FakeToastManager()
    flow = _make_save_flow(mgr, sync_fallback=True)
    options = {"output_dir": "/tmp", "file_name": "img", "format": "PNG"}

    def _sync():
        raise RuntimeError(SAVE_CANCELED_MESSAGE)

    noop = SimpleNamespace(
        kwargs={},
        signals=SimpleNamespace(
            progress=SimpleNamespace(connect=lambda *_a, **_k: None),
            result=SimpleNamespace(connect=lambda *_a, **_k: None),
            error=SimpleNamespace(connect=lambda *_a, **_k: None),
        ),
    )
    flow.start_with_worker(options, lambda _ev: noop, sync_fn=_sync)

    assert not flow._save_cancellation
    assert mgr.updated
    _tid, message, kwargs = mgr.updated[-1]
    assert "Canceled" in message
    assert kwargs["success"] is False
