"""Data models for multi-compare session — container-tree layout (i3/sway-style)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Union

import numpy as np


# ---- slots --------------------------------------------------------------------

@dataclass
class CompareSlot:
    """One image slot referenced by a Leaf in the layout tree."""

    id: int
    path: Path | None = None
    label: str = ""
    image: np.ndarray | None = None

    @property
    def is_loaded(self) -> bool:
        return self.image is not None


# ---- layout tree --------------------------------------------------------------

@dataclass
class LeafNode:
    """Holds a single image slot reference."""
    slot_id: int


@dataclass
class SplitNode:
    """A horizontal or vertical split with N children.

    direction:
        "h" — children laid out left-to-right (vertical dividers).
        "v" — children laid out top-to-bottom (horizontal dividers).
    weights: positive floats; effective share = w_i / sum(weights).
    """
    direction: str
    children: list  # list[LayoutNode]
    weights: list[float]

    def normalized_weights(self) -> list[float]:
        s = sum(self.weights) or 1.0
        return [w / s for w in self.weights]


LayoutNode = Union[LeafNode, SplitNode]


# ---- tree operations ----------------------------------------------------------

def leaves(node: LayoutNode | None) -> list[LeafNode]:
    if node is None:
        return []
    if isinstance(node, LeafNode):
        return [node]
    out: list[LeafNode] = []
    for child in node.children:
        out.extend(leaves(child))
    return out


def slot_ids_in_tree(node: LayoutNode | None) -> set[int]:
    return {leaf.slot_id for leaf in leaves(node)}


def find_path(node: LayoutNode | None, slot_id: int) -> list[int] | None:
    """Return list of child indices from root down to the leaf, or None."""
    if node is None:
        return None
    if isinstance(node, LeafNode):
        return [] if node.slot_id == slot_id else None
    for i, child in enumerate(node.children):
        sub = find_path(child, slot_id)
        if sub is not None:
            return [i, *sub]
    return None


def remove_leaf(node: LayoutNode | None, slot_id: int) -> LayoutNode | None:
    """Remove a leaf and collapse single-child splits."""
    if node is None:
        return None
    if isinstance(node, LeafNode):
        return None if node.slot_id == slot_id else node
    new_children: list = []
    new_weights: list[float] = []
    for child, w in zip(node.children, node.weights):
        result = remove_leaf(child, slot_id)
        if result is not None:
            new_children.append(result)
            new_weights.append(w)
    if not new_children:
        return None
    if len(new_children) == 1:
        return new_children[0]
    node.children = new_children
    node.weights = new_weights
    return node


def swap_slot_ids(node: LayoutNode | None, sid_a: int, sid_b: int) -> LayoutNode | None:
    """Swap the slot_ids of two leaves in-place (by identity rewrite)."""
    if node is None or sid_a == sid_b:
        return node
    if isinstance(node, LeafNode):
        if node.slot_id == sid_a:
            return LeafNode(sid_b)
        if node.slot_id == sid_b:
            return LeafNode(sid_a)
        return node
    node.children = [swap_slot_ids(c, sid_a, sid_b) for c in node.children]
    return node


def move_leaf(
    root: LayoutNode | None,
    source_slot_id: int,
    target_slot_id: int,
    side: str,
) -> LayoutNode | None:
    """Pluck source leaf and insert it beside target leaf on the given side."""
    if root is None or source_slot_id == target_slot_id:
        return root
    pruned = remove_leaf(root, source_slot_id)
    if pruned is None:
        return LeafNode(source_slot_id)
    return insert_beside(pruned, target_slot_id, side, source_slot_id)


def node_at_path(node: LayoutNode | None, path: tuple[int, ...]) -> LayoutNode | None:
    cur = node
    for i in path:
        if not isinstance(cur, SplitNode) or i < 0 or i >= len(cur.children):
            return None
        cur = cur.children[i]
    return cur


def _wrap_node(node: LayoutNode, side: str, new_slot_id: int) -> SplitNode:
    direction = "h" if side in ("left", "right") else "v"
    new_leaf = LeafNode(new_slot_id)
    children = [new_leaf, node] if side in ("left", "top") else [node, new_leaf]
    return SplitNode(direction=direction, children=children, weights=[1.0, 1.0])


def insert_beside_path(
    root: LayoutNode | None,
    path: tuple[int, ...],
    side: str,
    new_slot_id: int,
) -> LayoutNode | None:
    """Insert a new leaf beside the node at `path`. Path may point to a SplitNode.

    If the target's immediate parent split runs in the same direction as the
    requested side, the new leaf is added as a sibling there. Otherwise the
    target node is wrapped in a new orthogonal split.
    """
    if root is None:
        return LeafNode(new_slot_id)
    if not path:
        # Target is the root node; wrap it in a new orthogonal split.
        return _wrap_node(root, side, new_slot_id)

    # Walk to the parent of the target.
    parent = root
    for i in path[:-1]:
        assert isinstance(parent, SplitNode)
        parent = parent.children[i]
    assert isinstance(parent, SplitNode)
    idx = path[-1]
    target = parent.children[idx]
    wanted_dir = "h" if side in ("left", "right") else "v"

    if wanted_dir == parent.direction:
        avg_w = sum(parent.weights) / len(parent.weights) if parent.weights else 1.0
        ins_at = idx if side in ("left", "top") else idx + 1
        parent.children.insert(ins_at, LeafNode(new_slot_id))
        parent.weights.insert(ins_at, avg_w)
        return root

    parent.children[idx] = _wrap_node(target, side, new_slot_id)
    return root


def insert_beside(
    node: LayoutNode | None,
    target_slot_id: int,
    side: str,
    new_slot_id: int,
) -> LayoutNode | None:
    """Insert a new leaf beside the leaf with target_slot_id.

    side: "left" | "right" | "top" | "bottom".

    If the immediate parent split already runs in the same direction, the new
    leaf is added as a sibling in that split instead of nesting another split.
    """
    if node is None:
        return LeafNode(new_slot_id)

    if isinstance(node, LeafNode):
        if node.slot_id != target_slot_id:
            return node
        direction = "h" if side in ("left", "right") else "v"
        new_leaf = LeafNode(new_slot_id)
        children = [new_leaf, node] if side in ("left", "top") else [node, new_leaf]
        return SplitNode(direction=direction, children=children, weights=[1.0, 1.0])

    # Split: walk into the child that contains target.
    for i, child in enumerate(node.children):
        if find_path(child, target_slot_id) is None:
            continue
        # If we're at the immediate parent of the leaf and the parent's direction
        # matches the side → flatten by adding as sibling rather than nesting.
        if isinstance(child, LeafNode) and child.slot_id == target_slot_id:
            wanted_dir = "h" if side in ("left", "right") else "v"
            if wanted_dir == node.direction:
                # Insert sibling in this split.
                avg_w = sum(node.weights) / len(node.weights)
                if side in ("left", "top"):
                    node.children.insert(i, LeafNode(new_slot_id))
                    node.weights.insert(i, avg_w)
                else:
                    node.children.insert(i + 1, LeafNode(new_slot_id))
                    node.weights.insert(i + 1, avg_w)
                return node
        # Otherwise recurse.
        node.children[i] = insert_beside(child, target_slot_id, side, new_slot_id)
        return node
    return node


# ---- state --------------------------------------------------------------------

@dataclass
class MultiCompareState:
    """State for the multi-compare view."""

    slots: list[CompareSlot] = field(default_factory=list)
    root: LayoutNode | None = None
    focused_slot_id: int | None = None
    zoom: float = 1.0
    pan_x: float = 0.0
    pan_y: float = 0.0
    max_slots: int = 12

    drag_active: bool = False
    drag_target_path: tuple[int, ...] | None = None  # node path in the tree
    drag_target_side: str | None = None  # "left"|"right"|"top"|"bottom"|"center"
    drag_target_root: bool = False  # True when tree is empty: drop creates root leaf
    drag_target_swap_slot_id: int | None = None  # set when side="center" (internal swap)
    drag_internal: bool = False  # True for in-app slot drag (swap/move), False for file DnD
    drag_source_slot_id: int | None = None  # set during internal drag

    @property
    def is_focused(self) -> bool:
        return self.focused_slot_id is not None

    def slot_count(self) -> int:
        return len(slot_ids_in_tree(self.root))
