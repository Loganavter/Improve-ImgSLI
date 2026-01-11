import logging
from typing import List, Any

logger = logging.getLogger("ImproveImgSLI")

class VideoEditorService:
    def __init__(self, initial_snapshots: List[Any]):

        self._all_snapshots = initial_snapshots

        self._current_snapshots = list(initial_snapshots)

        self._undo_stack = []
        self._redo_stack = []

    def get_frame_count(self):
        return len(self._current_snapshots)

    def get_snapshot_at(self, index):
        if 0 <= index < len(self._current_snapshots):
            return self._current_snapshots[index]
        return None

    def get_current_snapshots(self):
        return self._current_snapshots

    def delete_selection(self, start_idx: int, end_idx: int):
        if start_idx < 0: start_idx = 0
        count = len(self._current_snapshots)
        if end_idx >= count: end_idx = count - 1

        s = min(start_idx, end_idx)
        e = max(start_idx, end_idx)

        self._undo_stack.append(list(self._current_snapshots))
        self._redo_stack.clear()

        left_part = self._current_snapshots[:s]
        right_part = self._current_snapshots[e + 1:]

        self._current_snapshots = left_part + right_part
        return True

    def undo(self):
        if not self._undo_stack:
            return False

        self._redo_stack.append(list(self._current_snapshots))
        self._current_snapshots = self._undo_stack.pop()
        return True

    def redo(self):
        if not self._redo_stack:
            return False

        self._undo_stack.append(list(self._current_snapshots))
        self._current_snapshots = self._redo_stack.pop()
        return True

    def can_undo(self):
        return len(self._undo_stack) > 0

    def can_redo(self):
        return len(self._redo_stack) > 0

