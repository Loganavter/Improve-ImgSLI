"""Multi Compare button multi-add placement parity with DnD (B2 close-out).

Residual H1 defect on the refactored tree: ``dialog_add.load_images``
re-resolved its auto target against the live widget for *every* file, but
the ``transact`` commits only after the planning loop — files 1..N read the
pre-confirm tree (stale anchor) and each ``((), side)`` re-hit wrapped the
whole root instead of sibling-chaining (``S(h,[S(h,[L0,L1]),L2])`` — uneven
panes vs DnD's flat chain). Only file 0 may read the live canvas now;
files 1..N chain beside the previously added slot via ``find_path`` on the
scratch state (same rule as ``loading.on_images_dropped``).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from tabs.multi_compare.controller import MultiCompareController
from tabs.multi_compare.models import LeafNode, MultiCompareState, SplitNode
from tabs.multi_compare.scene import actions as mc_actions
from tabs.multi_compare.scene.store import reduce as mc_reduce
from tabs.multi_compare.use_cases import loading as loading_use_cases


class _CapturingPool:
    def __init__(self):
        self.workers: list = []

    def start(self, worker):
        self.workers.append(worker)

    def run_all(self, limit: int = 30) -> None:
        for _ in range(limit):
            if not self.workers:
                return
            self.workers.pop(0).run()


class _FakeToastManager:
    def __init__(self):
        self._next_id = 0
        self.shown: list = []
        self.updated: list = []
        self.closed: list = []

    def show_toast(self, message, **kwargs):
        self._next_id += 1
        self.shown.append((self._next_id, message, kwargs))
        return self._next_id

    def update_toast(self, toast_id, message, **kwargs):
        self.updated.append((toast_id, message, kwargs))

    def close_toast(self, toast_id):
        self.closed.append(toast_id)


class _FakeMcStore:
    """Dispatch-only mutation through the real pure reducer (STORE invariants)."""

    def __init__(self, state=None):
        self.state = state or MultiCompareState()
        self.transacts = 0

    def dispatch(self, action):
        self.state = mc_reduce(self.state, action)

    def transact(self, actions_list):
        self.transacts += 1
        for sub in actions_list:
            self.dispatch(sub)
        return self.state


class _ColdWidget:
    """Headless widget with a cold canvas: no live geometry (dead-geometry H1)."""

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


class _StaleWidget(_ColdWidget):
    """Warm-canvas simulation: live auto target answers once (pre-confirm
    tree), then goes stale — every re-read returns the same pre-confirm
    anchor like the uncommitted live canvas does mid-``transact``."""

    def __init__(self, mc_store, anchor):
        super().__init__(mc_store)
        self._anchor = anchor
        self.auto_reads = 0

    def _pick_auto_target(self, leaf_entries=None):
        self.auto_reads += 1
        return self._anchor


def _make_controller(widget):
    toast_manager = _FakeToastManager()
    pool = _CapturingPool()
    emitted: list = []
    event_bus = SimpleNamespace(
        emitted=emitted,
        emit=lambda e: emitted.append(e),
        subscribe=lambda *a, **k: None,
    )
    context = SimpleNamespace(
        main_window=SimpleNamespace(toast_manager=toast_manager),
        thread_pool=pool,
        event_bus=event_bus,
    )
    store = SimpleNamespace(settings=SimpleNamespace(auto_crop_black_borders=False))
    controller = MultiCompareController(widget, store=store, context=context)
    return controller, pool, toast_manager, event_bus


def _png(tmp_path, name, size=(800, 600)):
    path = tmp_path / name
    Image.new("RGB", size, (10, 120, 200)).save(path)
    return path


def _tree_repr(node) -> str:
    if node is None:
        return "None"
    if isinstance(node, LeafNode):
        return f"L({node.slot_id})"
    assert isinstance(node, SplitNode)
    return f"S({node.direction},[{','.join(_tree_repr(c) for c in node.children)}])"


def test_button_single_matches_dnd_on_empty_canvas(tmp_path):
    """Placement parity, single file: button ≡ DnD-on-empty-canvas (one leaf)."""
    path = _png(tmp_path, "one.png")

    mc_store = _FakeMcStore()
    controller, _, _, _ = _make_controller(_ColdWidget(mc_store))
    assert controller.load_images([path]) == 1
    button_tree = _tree_repr(mc_store.state.root)
    button_slots = [s.path for s in mc_store.state.slots]

    mc_store2 = _FakeMcStore()
    controller2, _, _, _ = _make_controller(_ColdWidget(mc_store2))
    loading_use_cases.on_images_dropped(controller2, [path], (None, False), None)
    assert _tree_repr(mc_store2.state.root) == button_tree == "L(0)"
    assert [s.path for s in mc_store2.state.slots] == button_slots


def test_button_multi_matches_dnd_on_empty_canvas(tmp_path):
    """Placement parity, multi-file: button ≡ DnD-on-empty-canvas (flat chain)."""
    paths = [_png(tmp_path, f"img{i}.png") for i in range(3)]

    mc_store = _FakeMcStore()
    controller, _, _, _ = _make_controller(_ColdWidget(mc_store))
    assert controller.load_images(list(paths)) == 3
    button_tree = _tree_repr(mc_store.state.root)

    mc_store2 = _FakeMcStore()
    controller2, _, _, _ = _make_controller(_ColdWidget(mc_store2))
    loading_use_cases.on_images_dropped(controller2, list(paths), (None, False), None)
    assert _tree_repr(mc_store2.state.root) == button_tree
    # Flat single split — no nested wrap (even panes, not "криво").
    assert button_tree == "S(v,[L(0),L(1),L(2)])"
    assert [s.path for s in mc_store.state.slots] == [
        s.path for s in mc_store2.state.slots
    ]


def test_button_multi_add_chains_beside_last_added_not_stale_anchor(tmp_path):
    """Files 1..N chain beside the previously added slot even when the live
    canvas keeps answering the stale pre-confirm anchor (the B2 losing step:
    every file re-reading live geometry wrapped the root per file)."""
    first = _png(tmp_path, "first.png")
    paths = [_png(tmp_path, f"new{i}.png") for i in range(2)]

    mc_store = _FakeMcStore()
    mc_store.dispatch(
        mc_actions.add_slot(
            path=first, label="first",
            target_path=None, side=None, target_root=True,
        )
    )
    widget = _StaleWidget(mc_store, ((), "right"))
    controller, _, _, _ = _make_controller(widget)

    assert controller.load_images(list(paths)) == 2
    # File 0 beside L0 (live anchor), file 1 beside file 0 — flat, not nested.
    assert _tree_repr(mc_store.state.root) == "S(h,[L(0),L(1),L(2)])"
    # Only file 0 may read live geometry; the chain reads scratch state.
    assert widget.auto_reads == 1


def test_button_multi_add_is_single_transact(tmp_path):
    """A3 guard holds on the fixed path: one confirm = one transact."""
    paths = [_png(tmp_path, f"t{i}.png") for i in range(3)]
    mc_store = _FakeMcStore()
    controller, _, _, _ = _make_controller(_ColdWidget(mc_store))
    controller.load_images(list(paths))
    assert mc_store.transacts == 1


def test_button_multi_add_partial_overflow_still_places_fittable(tmp_path):
    """Grid with 1 free slot + 2-file confirm: first file lands, second
    surfaces a grid-full error-toast (never silent, never misplaced)."""
    first = _png(tmp_path, "first.png")
    full_state = MultiCompareState(max_slots=2)
    mc_store = _FakeMcStore(full_state)
    mc_store.dispatch(
        mc_actions.add_slot(
            path=first, label="first",
            target_path=None, side=None, target_root=True,
        )
    )
    widget = _ColdWidget(mc_store)
    controller, _, _, event_bus = _make_controller(widget)

    created = controller.load_images(
        [_png(tmp_path, "ok.png"), _png(tmp_path, "over.png")]
    )
    assert created == 1
    assert len(mc_store.state.slots) == 2
    assert len(event_bus.emitted) == 1
    assert "over.png" in str(getattr(event_bus.emitted[0], "error", event_bus.emitted[0]))
