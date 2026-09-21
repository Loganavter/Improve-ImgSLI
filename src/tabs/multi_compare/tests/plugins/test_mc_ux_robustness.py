"""Multi Compare UX robustness: overflow coalescing + restore validation.

1. A 100-file drop onto a nearly-full grid surfaces exactly ONE summary
   dialog per gesture (not one ``CoreErrorOccurredEvent`` per skipped file).
2. ``deserialize_session`` skips malformed slot entries with a warning and
   restores the well-formed rest — a corrupt entry (or an unknown version)
   never aborts the session restore, so ``project_io``'s per-session loop
   continues past bad sessions.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from tabs.multi_compare.controller import MultiCompareController
from tabs.multi_compare.models import MultiCompareState
from tabs.multi_compare.scene import actions as mc_actions
from tabs.multi_compare.use_cases import loading as loading_use_cases
from tabs.multi_compare.use_cases import persistence as mc_persistence


class _CapturingPool:
    def __init__(self):
        self.workers: list = []

    def start(self, worker):
        self.workers.append(worker)


class _FakeToastManager:
    def __init__(self):
        self._next_id = 0

    def show_toast(self, message, **kwargs):
        self._next_id += 1
        return self._next_id

    def update_toast(self, toast_id, message, **kwargs):
        pass

    def close_toast(self, toast_id):
        pass


class _FakeMcStore:
    """Dispatch-only mutation through the real pure reducer (STORE invariants)."""

    def __init__(self, state=None):
        from tabs.multi_compare.scene.store import reduce as mc_reduce

        self._reduce = mc_reduce
        self.state = state or MultiCompareState()
        self.transacts = 0

    def dispatch(self, action):
        self.state = self._reduce(self.state, action)

    def transact(self, actions_list):
        self.transacts += 1
        for sub in actions_list:
            self.dispatch(sub)
        return self.state


class _ColdWidget:
    """Headless widget with a cold canvas (no live geometry)."""

    def __init__(self, mc_store):
        self.store = mc_store
        self.canvas = SimpleNamespace(request_view_update=lambda: None)
        self.images_dropped = SimpleNamespace(connect=lambda *_: None)
        self.add_requested = SimpleNamespace(connect=lambda *_: None)
        self.save_requested = SimpleNamespace(connect=lambda *_: None)
        self.quick_save_requested = SimpleNamespace(connect=lambda *_: None)
        self.settings_requested = SimpleNamespace(connect=lambda *_: None)
        self.help_requested = SimpleNamespace(connect=lambda *_: None)
        self.divider_color_picker_requested = SimpleNamespace(connect=lambda *_: None)

    @property
    def state(self):
        return self.store.state


def _make_controller(widget):
    emitted: list = []
    event_bus = SimpleNamespace(
        emitted=emitted,
        emit=lambda e: emitted.append(e),
        subscribe=lambda *a, **k: None,
    )
    context = SimpleNamespace(
        main_window=SimpleNamespace(toast_manager=_FakeToastManager()),
        thread_pool=_CapturingPool(),
        event_bus=event_bus,
    )
    store = SimpleNamespace(settings=SimpleNamespace(auto_crop_black_borders=False))
    controller = MultiCompareController(widget, store=store, context=context)
    return controller, event_bus


def _png(tmp_path, name):
    path = tmp_path / name
    Image.new("RGB", (4, 4), (10, 120, 200)).save(path)
    return path


def test_hundred_file_drop_onto_nearly_full_grid_emits_single_dialog(tmp_path):
    """100-file drop with 1 free cell: 1 slot lands, exactly 1 dialog."""
    mc_store = _FakeMcStore(MultiCompareState(max_slots=4))
    for i in range(3):
        first = _png(tmp_path, f"seed{i}.png")
        mc_store.dispatch(
            mc_actions.add_slot(
                path=first, label=f"seed{i}",
                target_path=None, side=None, target_root=True,
            )
        )
    controller, event_bus = _make_controller(_ColdWidget(mc_store))

    paths = [_png(tmp_path, f"drop{i:03d}.png") for i in range(100)]
    loading_use_cases.on_images_dropped(controller, paths, (None, False), None)

    assert len(mc_store.state.slots) == 4
    assert len(event_bus.emitted) == 1
    message = str(getattr(event_bus.emitted[0], "error", event_bus.emitted[0]))
    assert "99 files" in message
    assert "drop001.png" in message


def test_dialog_add_overflow_coalesces_to_single_summary(tmp_path):
    """Dialog confirm past capacity: fittable files land, 1 summary dialog."""
    mc_store = _FakeMcStore(MultiCompareState(max_slots=2))
    first = _png(tmp_path, "first.png")
    mc_store.dispatch(
        mc_actions.add_slot(
            path=first, label="first",
            target_path=None, side=None, target_root=True,
        )
    )
    controller, event_bus = _make_controller(_ColdWidget(mc_store))

    created = controller.load_images(
        [_png(tmp_path, "ok.png"), _png(tmp_path, "over1.png"), _png(tmp_path, "over2.png")]
    )
    assert created == 1
    assert len(mc_store.state.slots) == 2
    assert len(event_bus.emitted) == 1
    message = str(getattr(event_bus.emitted[0], "error", event_bus.emitted[0]))
    assert "2 files" in message
    assert "over1.png" in message
    assert "over2.png" in message


class _SessionStore:
    def __init__(self):
        self.saved: dict = {}

    def set_session_state_slot(self, slot, state, *, session_id=None, emit_scope=None):
        self.saved[session_id] = state


def _restore(data) -> MultiCompareState:
    store = _SessionStore()
    context = SimpleNamespace(store=store)
    mc_persistence.deserialize_session(SimpleNamespace(), "s1", data, context)
    return store.saved["s1"]


def test_corrupt_slot_entries_restore_rest():
    """Malformed entries skip-and-log; well-formed siblings restore."""
    data = {
        "version": 1,
        "slots": [
            {"id": 1, "path": "/a.png", "label": "a"},
            {"bogus": True},
            {"id": "x", "path": "/bad.png"},
            {"id": 2, "path": 123},
            "not-a-dict",
            {"id": 3, "path": None, "label": "c"},
            {"id": 4, "path": "/d.png", "label": 7},
        ],
        "root": {"type": "leaf", "slot_id": 1},
        "zoom": "bad",
        "max_slots": 12,
    }
    state = _restore(data)
    assert [s.id for s in state.slots] == [1, 3, 4]
    assert state.slots[2].label == "7"
    assert state.zoom == 1.0


def test_unknown_version_still_restores_known_fields():
    """Forward-compat: version is read (and noted), known fields restore."""
    data = {
        "version": 99,
        "slots": [{"id": 1, "path": "/a.png", "label": "a"}],
        "root": "junk",
        "max_slots": 12,
    }
    state = _restore(data)
    assert [s.id for s in state.slots] == [1]
    assert state.root is None
