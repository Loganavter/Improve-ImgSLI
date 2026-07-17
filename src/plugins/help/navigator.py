"""Navigation stack for hierarchical help browsing."""

from __future__ import annotations

from plugins.help.tree import HelpTree


class HelpNavigator:
    """Stack of node ids from root toward the current topic.

    ``pop`` / ``go_forward`` support browser-style mouse Back/Forward buttons
    via a separate forward stack that is cleared on any new drill-down.
    """

    def __init__(self, tree: HelpTree) -> None:
        self._tree = tree
        self._stack: list[str] = [tree.root_id]
        self._forward: list[str] = []

    @property
    def stack(self) -> tuple[str, ...]:
        return tuple(self._stack)

    @property
    def current_id(self) -> str:
        return self._stack[-1]

    def current_node(self):
        return self._tree.require(self.current_id)

    def breadcrumb(self) -> tuple[tuple[str, str], ...]:
        """``(node_id, title)`` for each stack entry."""
        return tuple(
            (nid, self._tree.require(nid).title) for nid in self._stack
        )

    def reset(self) -> None:
        self._stack = [self._tree.root_id]
        self._forward.clear()

    def push(self, node_id: str) -> None:
        target = self._tree.resolve_alias(node_id)
        if target == self.current_id:
            return
        # If target is already on the stack, trim to it.
        if target in self._stack:
            self._stack = self._stack[: self._stack.index(target) + 1]
            self._forward.clear()
            return
        path = self._tree.path_to(target)
        self._stack = list(path)
        self._forward.clear()

    def pop(self) -> str | None:
        if len(self._stack) <= 1:
            return None
        left = self._stack.pop()
        self._forward.append(left)
        return self.current_id

    def go_forward(self) -> str | None:
        if not self._forward:
            return None
        nxt = self._forward.pop()
        if nxt == self.current_id:
            return self.current_id
        if nxt in self._stack:
            self._stack = self._stack[: self._stack.index(nxt) + 1]
            return self.current_id
        # Re-enter the left node as the next breadcrumb tip when it is a
        # child of the current node; otherwise rebuild the path.
        children = {c.node_id for c in self._tree.children_of(self.current_id)}
        if nxt in children:
            self._stack.append(nxt)
        else:
            self._stack = list(self._tree.path_to(nxt))
        return self.current_id

    def pop_to(self, node_id: str) -> None:
        target = self._tree.resolve_alias(node_id)
        if target in self._stack:
            trimmed = self._stack[self._stack.index(target) + 1 :]
            self._stack = self._stack[: self._stack.index(target) + 1]
            # Soft forward: deepest tip first so Forward restores it last-out.
            self._forward.extend(reversed(trimmed))
            return
        self.push(target)

    def replace_sibling(self, sibling_id: str) -> None:
        """Stay at the same depth; switch to another child of the same parent."""
        sibling = self._tree.resolve_alias(sibling_id)
        self._forward.clear()
        if len(self._stack) <= 1:
            self.push(sibling)
            return
        parent = self._stack[-2]
        children = {c.node_id for c in self._tree.children_of(parent)}
        if sibling not in children:
            self.push(sibling)
            return
        self._stack = [*self._stack[:-1], sibling]

    def can_go_back(self) -> bool:
        return len(self._stack) > 1

    def can_go_forward(self) -> bool:
        return bool(self._forward)
