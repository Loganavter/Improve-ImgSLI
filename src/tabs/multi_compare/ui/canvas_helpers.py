"""Shared chrome helpers for multi-compare canvas (no Qt widget deps)."""

from __future__ import annotations

from tabs.multi_compare.models import LeafNode, SplitNode

INTERNAL_SLOT_MIME = "application/x-imgsli-multi-slot"


def layout_is_symmetric(node) -> bool:
    if node is None or isinstance(node, LeafNode):
        return True
    if not isinstance(node, SplitNode):
        return True
    ws = node.normalized_weights()
    if ws:
        target = 1.0 / len(ws)
        if any(abs(w - target) > 1e-4 for w in ws):
            return False
    return all(layout_is_symmetric(c) for c in node.children)


def dividers_locked(state) -> bool:
    if getattr(state, "zoom", 1.0) <= 1.0:
        return True
    return layout_is_symmetric(state.root)


# Compat aliases used by feature gestures / older imports.
_layout_is_symmetric = layout_is_symmetric
_dividers_locked = dividers_locked
