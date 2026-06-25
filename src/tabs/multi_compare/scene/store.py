"""Local Redux-style store for the multi-compare tab.

The tab keeps its own action/reducer space rather than extending the global
``ActionType`` enum used by main compare: the multi-compare layout, slots and
drag state are orthogonal to the rest of the app, and bolting a dozen tab-only
actions into the global enum bloats it for one consumer.

Pattern matches :mod:`core.state_management.dispatcher`: pure ``reduce`` returns
a new state, subscribers receive the (action, new_state) pair after the swap so
they can rebuild render plans / refresh widgets.

State is a frozen ``MultiCompareState`` dataclass; the only path to a new
state is ``dispatch(action)`` which runs the reducer and notifies subscribers.
"""

from __future__ import annotations

import dataclasses
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import numpy as np

from tabs.multi_compare.models import (
    CompareSlot,
    LayoutNode,
    LeafNode,
    MultiCompareLabelSettings,
    MultiCompareState,
    slot_ids_in_tree,
)
from tabs.multi_compare.scene import layout_constraints, tree_ops

logger = logging.getLogger("ImproveImgSLI")


# ---- actions ------------------------------------------------------------------


@dataclass(frozen=True)
class MultiCompareAction:
    """Base for all multi-compare actions.

    ``type`` is a stable string so logs / dev tools can show a readable label.
    Concrete subclasses add their own payload fields.
    """

    type: str


@dataclass(frozen=True)
class AddSlot(MultiCompareAction):
    path: Path
    image: np.ndarray
    label: str
    target_path: tuple[int, ...] | None  # None → wrap-root / first
    side: str | None  # "left"|"right"|"top"|"bottom" or None for auto
    target_root: bool


@dataclass(frozen=True)
class RemoveSlot(MultiCompareAction):
    slot_id: int


@dataclass(frozen=True)
class RenameSlot(MultiCompareAction):
    slot_id: int
    label: str


@dataclass(frozen=True)
class SwapSlots(MultiCompareAction):
    slot_id_a: int
    slot_id_b: int


@dataclass(frozen=True)
class MoveSlot(MultiCompareAction):
    source_slot_id: int
    target_path: tuple[int, ...]
    target_anchor_slot_id: int
    side: str


@dataclass(frozen=True)
class SetFocus(MultiCompareAction):
    slot_id: int | None  # None → clear focus


@dataclass(frozen=True)
class SetZoom(MultiCompareAction):
    zoom: float
    pan_x: float
    pan_y: float


@dataclass(frozen=True)
class SetPan(MultiCompareAction):
    pan_x: float
    pan_y: float


@dataclass(frozen=True)
class ResetView(MultiCompareAction):
    pass


@dataclass(frozen=True)
class SetDragState(MultiCompareAction):
    active: bool
    internal: bool
    source_slot_id: int | None
    target_path: tuple[int, ...] | None
    target_side: str | None
    target_root: bool
    target_swap_slot_id: int | None


@dataclass(frozen=True)
class SetSplitWeights(MultiCompareAction):
    path: tuple[int, ...]
    weights: tuple[float, ...]


@dataclass(frozen=True)
class SetLabelSettings(MultiCompareAction):
    settings: MultiCompareLabelSettings


@dataclass(frozen=True)
class ApplyLayoutTree(MultiCompareAction):
    """Replace the whole tree (used by tests / snapshot restore)."""

    root: LayoutNode | None


@dataclass(frozen=True)
class Clear(MultiCompareAction):
    pass


class actions:
    """Convenience factories so call sites don't pass ``type=`` everywhere."""

    @staticmethod
    def add_slot(
        path: Path,
        image: np.ndarray,
        label: str,
        target_path: tuple[int, ...] | None = None,
        side: str | None = None,
        target_root: bool = False,
    ) -> AddSlot:
        return AddSlot(
            type="multi_compare/add_slot",
            path=path,
            image=image,
            label=label,
            target_path=target_path,
            side=side,
            target_root=target_root,
        )

    @staticmethod
    def remove_slot(slot_id: int) -> RemoveSlot:
        return RemoveSlot(type="multi_compare/remove_slot", slot_id=slot_id)

    @staticmethod
    def rename_slot(slot_id: int, label: str) -> RenameSlot:
        return RenameSlot(
            type="multi_compare/rename_slot",
            slot_id=slot_id,
            label=label,
        )

    @staticmethod
    def swap_slots(slot_id_a: int, slot_id_b: int) -> SwapSlots:
        return SwapSlots(
            type="multi_compare/swap_slots",
            slot_id_a=slot_id_a,
            slot_id_b=slot_id_b,
        )

    @staticmethod
    def move_slot(
        source_slot_id: int,
        target_path: tuple[int, ...],
        target_anchor_slot_id: int,
        side: str,
    ) -> MoveSlot:
        return MoveSlot(
            type="multi_compare/move_slot",
            source_slot_id=source_slot_id,
            target_path=target_path,
            target_anchor_slot_id=target_anchor_slot_id,
            side=side,
        )

    @staticmethod
    def set_focus(slot_id: int | None) -> SetFocus:
        return SetFocus(type="multi_compare/set_focus", slot_id=slot_id)

    @staticmethod
    def set_zoom(zoom: float, pan_x: float, pan_y: float) -> SetZoom:
        return SetZoom(
            type="multi_compare/set_zoom",
            zoom=zoom,
            pan_x=pan_x,
            pan_y=pan_y,
        )

    @staticmethod
    def set_pan(pan_x: float, pan_y: float) -> SetPan:
        return SetPan(type="multi_compare/set_pan", pan_x=pan_x, pan_y=pan_y)

    @staticmethod
    def reset_view() -> ResetView:
        return ResetView(type="multi_compare/reset_view")

    @staticmethod
    def set_drag_state(
        *,
        active: bool,
        internal: bool = False,
        source_slot_id: int | None = None,
        target_path: tuple[int, ...] | None = None,
        target_side: str | None = None,
        target_root: bool = False,
        target_swap_slot_id: int | None = None,
    ) -> SetDragState:
        return SetDragState(
            type="multi_compare/set_drag_state",
            active=active,
            internal=internal,
            source_slot_id=source_slot_id,
            target_path=target_path,
            target_side=target_side,
            target_root=target_root,
            target_swap_slot_id=target_swap_slot_id,
        )

    @staticmethod
    def set_split_weights(
        path: tuple[int, ...], weights: tuple[float, ...] | list[float]
    ) -> SetSplitWeights:
        return SetSplitWeights(
            type="multi_compare/set_split_weights",
            path=tuple(path),
            weights=tuple(weights),
        )

    @staticmethod
    def set_label_settings(settings: MultiCompareLabelSettings) -> SetLabelSettings:
        return SetLabelSettings(
            type="multi_compare/set_label_settings",
            settings=settings,
        )

    @staticmethod
    def apply_layout_tree(root: LayoutNode | None) -> ApplyLayoutTree:
        return ApplyLayoutTree(type="multi_compare/apply_layout_tree", root=root)

    @staticmethod
    def clear() -> Clear:
        return Clear(type="multi_compare/clear")


# ---- reducer ------------------------------------------------------------------


def _next_slot_id(state: MultiCompareState) -> int:
    if not state.slots:
        return 0
    return max(s.id for s in state.slots) + 1


def _replace(state: MultiCompareState, **changes) -> MultiCompareState:
    """Shallow ``dataclasses.replace`` that preserves the legacy list identity
    of ``slots`` when not changed — important while the canvas still reads the
    same list reference between dispatches."""
    return dataclasses.replace(state, **changes)


def reduce(state: MultiCompareState, action: MultiCompareAction) -> MultiCompareState:
    """Pure reducer: ``state + action → new_state`` (or same instance when no-op)."""
    if isinstance(action, AddSlot):
        if len(state.slots) >= state.max_slots:
            return state
        slot_id = _next_slot_id(state)
        slot = CompareSlot(
            id=slot_id,
            path=action.path,
            label=action.label or (action.path.stem if action.path else ""),
            image=action.image,
        )
        new_slots = list(state.slots) + [slot]
        if action.target_root or state.root is None:
            new_root: LayoutNode | None = LeafNode(slot_id)
        elif action.target_path is not None and action.side is not None:
            new_root = tree_ops.insert_beside_path(
                state.root, action.target_path, action.side, slot_id
            )
        else:
            # caller did not pick a target — keep current root; widget layer
            # picks a target via its layout cache (auto-target needs widget
            # rects, which the reducer cannot see)
            new_root = state.root
        return _replace(state, slots=new_slots, root=new_root)

    if isinstance(action, RemoveSlot):
        new_slots = [s for s in state.slots if s.id != action.slot_id]
        new_root = tree_ops.remove_leaf(state.root, action.slot_id)
        focused = (
            None
            if state.focused_slot_id == action.slot_id
            else state.focused_slot_id
        )
        return _replace(state, slots=new_slots, root=new_root, focused_slot_id=focused)

    if isinstance(action, RenameSlot):
        new_slots = [
            dataclasses.replace(slot, label=action.label)
            if slot.id == action.slot_id
            else slot
            for slot in state.slots
        ]
        if new_slots == state.slots:
            return state
        return _replace(state, slots=new_slots)

    if isinstance(action, SwapSlots):
        new_root = tree_ops.swap_slot_ids(
            state.root, action.slot_id_a, action.slot_id_b
        )
        return _replace(state, root=new_root)

    if isinstance(action, MoveSlot):
        pruned = tree_ops.remove_leaf(state.root, action.source_slot_id)
        if pruned is None:
            return _replace(state, root=LeafNode(action.source_slot_id))
        # Anchor by slot id so the path stays meaningful after prune.
        from tabs.multi_compare.models import find_path

        new_anchor_path = find_path(pruned, action.target_anchor_slot_id)
        if new_anchor_path is None:
            return _replace(state, root=pruned)
        target_depth = len(action.target_path)
        new_path = tuple(new_anchor_path[:target_depth])
        new_root = tree_ops.insert_beside_path(
            pruned, new_path, action.side, action.source_slot_id
        )
        return _replace(state, root=new_root)

    if isinstance(action, SetFocus):
        if state.focused_slot_id == action.slot_id:
            return state
        return _replace(state, focused_slot_id=action.slot_id)

    if isinstance(action, SetZoom):
        if (
            state.zoom == action.zoom
            and state.pan_x == action.pan_x
            and state.pan_y == action.pan_y
        ):
            return state
        return _replace(
            state,
            zoom=action.zoom,
            pan_x=action.pan_x,
            pan_y=action.pan_y,
        )

    if isinstance(action, SetPan):
        if state.pan_x == action.pan_x and state.pan_y == action.pan_y:
            return state
        return _replace(state, pan_x=action.pan_x, pan_y=action.pan_y)

    if isinstance(action, ResetView):
        if state.zoom == 1.0 and state.pan_x == 0.0 and state.pan_y == 0.0:
            return state
        return _replace(state, zoom=1.0, pan_x=0.0, pan_y=0.0)

    if isinstance(action, SetDragState):
        return _replace(
            state,
            drag_active=action.active,
            drag_internal=action.internal,
            drag_source_slot_id=action.source_slot_id,
            drag_target_path=action.target_path,
            drag_target_side=action.target_side,
            drag_target_root=action.target_root,
            drag_target_swap_slot_id=action.target_swap_slot_id,
        )

    if isinstance(action, SetSplitWeights):
        weights = layout_constraints.constrain_split_weights(
            state.root,
            action.path,
            action.weights,
            state.slots,
            zoom=state.zoom,
        )
        new_root = tree_ops.set_split_weights(
            state.root, action.path, weights
        )
        if new_root is state.root:
            return state
        return _replace(state, root=new_root)

    if isinstance(action, SetLabelSettings):
        if state.label_settings == action.settings:
            return state
        return _replace(state, label_settings=action.settings)

    if isinstance(action, ApplyLayoutTree):
        if state.root is action.root:
            return state
        valid_ids = (
            slot_ids_in_tree(action.root) if action.root is not None else set()
        )
        focused = state.focused_slot_id if state.focused_slot_id in valid_ids else None
        return _replace(state, root=action.root, focused_slot_id=focused)

    if isinstance(action, Clear):
        return MultiCompareState()

    logger.warning("multi_compare reducer: unhandled action %s", type(action).__name__)
    return state


# ---- store --------------------------------------------------------------------


class MultiCompareStore:
    """Local dispatch loop for the multi-compare tab.

    Subscribers are called *after* the state swap with ``(action, new_state)``.
    The store does not enforce thread affinity — callers must dispatch on the
    GUI thread, mirroring the main app store.
    """

    def __init__(self, initial: MultiCompareState | None = None):
        self._state: MultiCompareState = initial or MultiCompareState()
        self._subscribers: list[Callable[[MultiCompareAction, MultiCompareState], None]] = []

    @property
    def state(self) -> MultiCompareState:
        return self._state

    def replace_state(self, state: MultiCompareState) -> None:
        """Swap the entire scene state in one shot (e.g. session restore).

        Notifies subscribers with a synthetic ``multi_compare/replace_state``
        action so listeners (canvas, etc.) re-sync without going through
        per-slot reducers.
        """
        self._state = state
        synthetic = MultiCompareAction(type="multi_compare/replace_state")
        for sub in list(self._subscribers):
            try:
                sub(synthetic, state)
            except Exception:
                logger.exception(
                    "multi_compare subscriber raised on replace_state",
                )

    def dispatch(self, action: MultiCompareAction) -> MultiCompareState:
        try:
            new_state = reduce(self._state, action)
        except Exception:
            logger.exception(
                "multi_compare dispatch failed: %s", getattr(action, "type", action)
            )
            return self._state
        if new_state is self._state:
            return self._state
        self._state = new_state
        for sub in list(self._subscribers):
            try:
                sub(action, new_state)
            except Exception:
                logger.exception(
                    "multi_compare subscriber raised on %s",
                    getattr(action, "type", action),
                )
        return new_state

    def subscribe(
        self,
        callback: Callable[[MultiCompareAction, MultiCompareState], None],
    ) -> Callable[[], None]:
        if callback not in self._subscribers:
            self._subscribers.append(callback)

        def unsubscribe() -> None:
            if callback in self._subscribers:
                self._subscribers.remove(callback)

        return unsubscribe
