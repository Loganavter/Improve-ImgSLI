"""MC tab P2 hygiene bundle (task-fix-mc-tab-p2-2026-09-20).

Covers:
* ``models.py`` carries no tree mutators (pure path is ``scene.tree_ops``);
  frozen-violation guard: ``tree_ops`` ops never mutate their input tree.
* context-menu failure signals: duplicate-full / duplicate-no-pixels /
  carry-miss report through the controller error channel, never silent.
* removal from the menu goes through the controller path (cancel-aware)
  with widget-direct fallback.
* ``DropQueue`` intake cap with one summary.
* full-res backlog (``_mc_full_queue``) cap with summary.
* ``MultiCompareStore.transact`` loud fallback when the core store has
  neither ``transact`` nor a dispatcher.

Headless-safe: no real dialogs/widgets; ``qapp`` fixture is a safety net.
"""

from __future__ import annotations

import ast
import logging
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication, QWidget

from tabs.multi_compare.models import (
    CompareSlot,
    LeafNode,
    MultiCompareState,
    SplitNode,
)
from tabs.multi_compare.scene import actions
from tabs.multi_compare.scene.store import MultiCompareStore
from ui.context_menu.models import ContextMenuRequest, ContextMenuTarget


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _tree() -> SplitNode:
    return SplitNode(
        direction="h",
        children=[
            LeafNode(1),
            SplitNode(
                direction="v",
                children=[LeafNode(2), LeafNode(3)],
                weights=[1.0, 1.0],
            ),
        ],
        weights=[1.0, 1.0],
    )


def _snapshot(node):
    """Structural snapshot (no pixels/identity) for purity comparison."""
    if node is None:
        return None
    if isinstance(node, LeafNode):
        return ("leaf", node.slot_id)
    return (
        "split",
        node.direction,
        [_snapshot(c) for c in node.children],
        list(node.weights),
    )


# --------------------------------------------------------------------------
# models: no mutators + tree_ops purity (frozen-violation guard)
# --------------------------------------------------------------------------


def test_models_has_no_tree_mutators():
    path = Path(__file__).resolve().parents[2] / "models.py"
    tree = ast.parse(path.read_text())
    defined = {
        n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
    }
    for banned in ("remove_leaf", "swap_slot_ids", "insert_beside", "insert_beside_path"):
        assert banned not in defined, f"models.{banned} must live in scene.tree_ops"


def test_tree_ops_remove_leaf_is_pure():
    from tabs.multi_compare.scene import tree_ops

    root = _tree()
    before = _snapshot(root)
    out = tree_ops.remove_leaf(root, 2)
    assert _snapshot(root) == before
    assert _snapshot(out) == (
        "split", "h", [("leaf", 1), ("leaf", 3)], [1.0, 1.0],
    )


def test_tree_ops_swap_slot_ids_is_pure():
    from tabs.multi_compare.scene import tree_ops

    root = _tree()
    before = _snapshot(root)
    out = tree_ops.swap_slot_ids(root, 1, 3)
    assert _snapshot(root) == before
    assert out is not root
    leaves = []

    def _collect(n):
        if isinstance(n, LeafNode):
            leaves.append(n.slot_id)
        else:
            for c in n.children:
                _collect(c)

    _collect(out)
    assert sorted(leaves) == [1, 2, 3]
    # Swap took effect: first leaf now carries id 3.
    assert isinstance(out, SplitNode)
    assert isinstance(out.children[0], LeafNode)
    assert out.children[0].slot_id == 3


def test_tree_ops_insert_beside_path_is_pure():
    from tabs.multi_compare.scene import tree_ops

    root = _tree()
    before = _snapshot(root)
    out = tree_ops.insert_beside_path(root, (0,), "right", 9)
    assert _snapshot(root) == before
    assert out is not root


# --------------------------------------------------------------------------
# context menu: failure signals + controller-path removal
# --------------------------------------------------------------------------


def _mc_widget(*, slots, root, controller=None, remove_slot=None):
    state = MultiCompareState(slots=list(slots), root=root)
    widget = SimpleNamespace(
        canvas=SimpleNamespace(pixel_cache=None),
        state=state,
        store=SimpleNamespace(dispatch=lambda a: None),
        remove_slot=remove_slot or (lambda slot_id: None),
        begin_pending_duplicate=lambda source_id: None,
        _translate=lambda key, default=None: default or key,
    )
    if controller is not None:
        widget._controller = controller
    return widget


def _mc_request(canvas, slot_id):
    return ContextMenuRequest(
        source_widget=canvas,
        global_pos=QPoint(0, 0),
        local_pos=QPoint(0, 0),
        session_type="multi_compare",
        target=ContextMenuTarget(kind="multi_compare_slot", id=slot_id),
    )


def _provider(widget):
    from tabs.multi_compare.context_menu import MultiCompareContextMenuProvider

    return MultiCompareContextMenuProvider(widget)


def test_duplicate_no_pixels_signals(qapp):
    reported: list = []
    controller = SimpleNamespace(report_user_error=reported.append)
    widget = _mc_widget(
        slots=[CompareSlot(id=1, path=Path("/x/1.png"), label="1")],
        root=LeafNode(1),
        controller=controller,
    )
    provider = _provider(widget)
    provider._has_pixels = lambda s: False
    provider._duplicate_slot(widget.state.slots[0])
    assert len(reported) == 1
    assert "duplicat" in reported[0].lower()


def test_carry_miss_signals(qapp):
    reported: list = []
    controller = SimpleNamespace(report_user_error=reported.append)
    widget = _mc_widget(
        slots=[CompareSlot(id=1, path=None, label="empty")],
        root=LeafNode(1),
        controller=controller,
    )
    provider = _provider(widget)
    provider._begin_carry(widget.state.slots[0])
    assert len(reported) == 1
    assert "carry" in reported[0].lower()


def test_remove_slot_prefers_controller_path(qapp):
    via: list = []
    controller = SimpleNamespace(remove_slot=lambda sid: via.append(("ctrl", sid)))
    widget_calls: list = []
    widget = _mc_widget(
        slots=[CompareSlot(id=1, path=Path("/x/1.png"), label="1")],
        root=LeafNode(1),
        controller=controller,
        remove_slot=lambda sid: widget_calls.append(sid),
    )
    provider = _provider(widget)
    assert provider.execute(
        "multi_compare.remove_slot", _mc_request(widget.canvas, 1), 1
    ) is True
    assert via == [("ctrl", 1)]
    assert widget_calls == []


def test_remove_slot_falls_back_to_widget(qapp):
    widget_calls: list = []
    widget = _mc_widget(
        slots=[CompareSlot(id=1, path=Path("/x/1.png"), label="1")],
        root=LeafNode(1),
        remove_slot=lambda sid: widget_calls.append(sid),
    )
    provider = _provider(widget)
    assert provider.execute(
        "multi_compare.remove_slot", _mc_request(widget.canvas, 1), 1
    ) is True
    assert widget_calls == [1]


# --------------------------------------------------------------------------
# DropQueue cap
# --------------------------------------------------------------------------


def _dnd_widget(*, slots, controller=None):
    state = MultiCompareState(slots=list(slots), root=None)
    emitted: list = []
    widget = SimpleNamespace(
        state=state,
        images_dropped=SimpleNamespace(emit=lambda *a: emitted.append(a)),
        _emitted_drops=emitted,
    )
    if controller is not None:
        widget._controller = controller
    return widget


def test_drop_queue_cap_trims_with_summary(qapp, monkeypatch):
    from tabs.multi_compare.ui import drag_drop as dnd

    reported: list = []
    controller = SimpleNamespace(report_user_error=reported.append)
    widget = _dnd_widget(slots=[], controller=controller)
    q = dnd.DropQueue()
    monkeypatch.setattr(dnd.DropQueue, "MAX_PENDING_PATHS", 3, raising=False)
    paths = [Path(f"/x/{i}.png") for i in range(5)]
    assert q.enqueue(0, paths, widget, (None, True), "right") is True
    assert q._pending_path_count() == 3
    assert len(reported) == 1
    assert "queue is full" in reported[0].lower()
    # CONTENT IDENTITY: first 3 kept in order, tail shed.
    # (Processing moves keys queued→inflight synchronously — delivery is
    # the deferred half — so identity is checked on the inflight keys.)
    assert q._inflight_keys == {(0, str(p)) for p in paths[:3]}


def test_drop_queue_all_capped_out_returns_false(qapp):
    from tabs.multi_compare.ui import drag_drop as dnd

    widget = _dnd_widget(slots=[])
    q = dnd.DropQueue()
    q.MAX_PENDING_PATHS = 0
    assert q.enqueue(0, [Path("/x/a.png")], widget, (None, True), "right") is False


# --------------------------------------------------------------------------
# full-res backlog cap
# --------------------------------------------------------------------------


def test_full_queue_cap_sheds_oldest_with_summary():
    from tabs.multi_compare.use_cases import preview_decode as pd

    reported: list = []
    controller = SimpleNamespace(
        _mc_full_queue=[(i, Path(f"/x/{i}.png"), False) for i in range(70)],
        report_user_error=reported.append,
    )
    pd._cap_full_queue(controller)
    assert len(controller._mc_full_queue) == pd._FULL_QUEUE_MAX
    # Oldest shed: newest 64 kept in order.
    assert controller._mc_full_queue[0][0] == 70 - pd._FULL_QUEUE_MAX
    assert len(reported) == 1
    assert "preview" in reported[0].lower()


def test_full_queue_under_cap_is_quiet():
    from tabs.multi_compare.use_cases import preview_decode as pd

    reported: list = []
    controller = SimpleNamespace(
        _mc_full_queue=[(1, Path("/x/1.png"), False)],
        report_user_error=reported.append,
    )
    pd._cap_full_queue(controller)
    assert len(controller._mc_full_queue) == 1
    assert reported == []


# --------------------------------------------------------------------------
# transact loud fallback
# --------------------------------------------------------------------------


def test_transact_without_batch_or_dispatcher_fails_loud(caplog):
    state = MultiCompareState(
        slots=[CompareSlot(id=1, path=Path("/x/1.png"), label="1")],
        root=LeafNode(1),
    )
    session = SimpleNamespace(state_slots={"multi_compare.state": state})
    core = SimpleNamespace(
        get_active_workspace_session=lambda: session,
        get_dispatcher=lambda: None,
    )
    store = MultiCompareStore(core_store=core)
    with caplog.at_level(logging.ERROR):
        out = store.transact(
            [actions.remove_slot(1), actions.rename_slot(1, "r")]
        )
    assert any(
        "neither transact nor dispatcher" in r.message for r in caplog.records
    )
    assert isinstance(out, MultiCompareState)
