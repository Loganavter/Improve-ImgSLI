"""Main widget for multi-compare tab — composes toolbar + GL grid + footer."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDragLeaveEvent, QDragMoveEvent, QDropEvent
from PySide6.QtWidgets import QVBoxLayout, QWidget

from tabs.multi_compare.models import (
    CompareSlot,
    LeafNode,
    MultiCompareState,
    find_path,
    insert_beside_path,
    remove_leaf,
    slot_ids_in_tree,
    swap_slot_ids,
)
from tabs.multi_compare.ui.footer import MultiCompareFooter
from tabs.multi_compare.ui.gl_grid import INTERNAL_SLOT_MIME, GLGridWidget
from tabs.multi_compare.ui.toolbar import MultiCompareToolbar

if TYPE_CHECKING:
    import numpy as np

_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp"}


class MultiCompareWidget(QWidget):
    """Composite widget: toolbar + GL grid + footer + smart DnD."""

    images_dropped = Signal(list, object, object)  # paths, (target_path, target_root), side
    add_requested = Signal()
    save_requested = Signal()

    def __init__(
        self,
        parent=None,
        *,
        add_images_text: str = "Add images",
        save_result_text: str = "Save result",
        translate=None,
    ):
        super().__init__(parent)
        self.state = MultiCompareState()

        self.setAcceptDrops(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(400, 300)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.toolbar = MultiCompareToolbar(self, text=add_images_text)
        self.gl_grid = GLGridWidget(self, translate=translate)
        self.footer = MultiCompareFooter(self, text=save_result_text)

        layout.addWidget(self.toolbar)
        layout.addWidget(self.gl_grid, 1)
        layout.addWidget(self.footer)

        self.toolbar.add_clicked.connect(self.add_requested)
        self.footer.save_clicked.connect(self.save_requested)

    def update_language(self, translate) -> None:
        self.toolbar.update_language(translate)
        self.footer.update_language(translate)

    def set_state(self, state: MultiCompareState) -> None:
        self.state = state
        self.gl_grid.set_state(state)

    # ---- tree mutations ----

    def _next_slot_id(self) -> int:
        if not self.state.slots:
            return 0
        return max(s.id for s in self.state.slots) + 1

    def add_image_auto(
        self, path: Path, image: "np.ndarray", label: str = ""
    ) -> int | None:
        """Append an image to the tree by splitting the largest leaf along its longer axis."""
        if len(self.state.slots) >= self.state.max_slots:
            return None
        slot_id = self._next_slot_id()
        slot = CompareSlot(id=slot_id, path=path, label=label or path.stem, image=image)
        self.state.slots.append(slot)
        if self.state.root is None:
            self.state.root = LeafNode(slot_id)
        else:
            target_path, side = self._pick_auto_target()
            self.state.root = insert_beside_path(
                self.state.root, target_path, side, slot_id
            )
        self.gl_grid.set_state(self.state)
        return slot_id

    def add_image_at(
        self,
        path: Path,
        image: "np.ndarray",
        label: str,
        target_path: tuple[int, ...] | None,
        side: str | None,
        target_root: bool,
    ) -> int | None:
        if len(self.state.slots) >= self.state.max_slots:
            return None
        slot_id = self._next_slot_id()
        slot = CompareSlot(id=slot_id, path=path, label=label or path.stem, image=image)
        self.state.slots.append(slot)
        if target_root or self.state.root is None:
            self.state.root = LeafNode(slot_id)
        elif target_path is not None and side is not None:
            self.state.root = insert_beside_path(
                self.state.root, target_path, side, slot_id
            )
        else:
            tp, side2 = self._pick_auto_target()
            self.state.root = insert_beside_path(self.state.root, tp, side2, slot_id)
        self.gl_grid.set_state(self.state)
        return slot_id

    def _pick_auto_target(self) -> tuple[tuple[int, ...], str]:
        """Pick the existing leaf with the largest rect; split along its longer axis."""
        entries = self.gl_grid._leaf_paths_and_rects()
        if not entries:
            return (), "right"
        leaf, rect, path = max(entries, key=lambda e: e[1].width() * e[1].height())
        side = "right" if rect.width() >= rect.height() else "bottom"
        return path, side

    def remove_slot(self, slot_id: int) -> None:
        self.state.slots = [s for s in self.state.slots if s.id != slot_id]
        self.state.root = remove_leaf(self.state.root, slot_id)
        if self.state.focused_slot_id == slot_id:
            self.state.focused_slot_id = None
        self.gl_grid.set_state(self.state)

    def reset_view(self) -> None:
        self.state.zoom = 1.0
        self.state.pan_x = 0.0
        self.state.pan_y = 0.0
        self.gl_grid.set_state(self.state)

    # ---- DnD ----

    def _has_image_urls(self, mime) -> bool:
        if not mime.hasUrls():
            return False
        for url in mime.urls():
            path = Path(url.toLocalFile())
            if path.suffix.lower() in _IMAGE_EXTENSIONS:
                return True
        return False

    def _has_internal_slot(self, mime) -> bool:
        return mime.hasFormat(INTERNAL_SLOT_MIME)

    def _internal_source_slot_id(self, mime) -> int | None:
        if not mime.hasFormat(INTERNAL_SLOT_MIME):
            return None
        try:
            return int(bytes(mime.data(INTERNAL_SLOT_MIME)).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return None

    def _grid_local_pos(self, pos):
        return self.gl_grid.mapFrom(self, pos)

    def _resolve_drop_target(self, pos, *, internal: bool):
        local = self._grid_local_pos(pos)
        if internal:
            return self.gl_grid.compute_drop_target(local, include_center=True)
        if len(slot_ids_in_tree(self.state.root)) >= self.state.max_slots:
            return None, None, False, None
        return self.gl_grid.compute_drop_target(local)

    def _apply_drag_preview(self, event, internal: bool) -> None:
        tgt_path, side, root_tgt, swap_id = self._resolve_drop_target(
            event.position().toPoint(), internal=internal
        )
        source_id = self._internal_source_slot_id(event.mimeData()) if internal else None
        self.state.drag_internal = internal
        self.state.drag_source_slot_id = source_id
        self.gl_grid.set_drag_state(True, tgt_path, side, root_tgt, swap_id)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if self._has_internal_slot(event.mimeData()):
            self._apply_drag_preview(event, internal=True)
            event.acceptProposedAction()
            return
        if self._has_image_urls(event.mimeData()):
            self._apply_drag_preview(event, internal=False)
            event.acceptProposedAction()
            return
        event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        if self._has_internal_slot(event.mimeData()):
            self._apply_drag_preview(event, internal=True)
            event.acceptProposedAction()
            return
        if self._has_image_urls(event.mimeData()):
            self._apply_drag_preview(event, internal=False)
            event.acceptProposedAction()
            return
        event.ignore()

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:
        self.state.drag_internal = False
        self.state.drag_source_slot_id = None
        self.gl_grid.set_drag_state(False, None, None, False, None)
        event.accept()

    def dropEvent(self, event: QDropEvent) -> None:
        mime = event.mimeData()
        if self._has_internal_slot(mime):
            source_id = self._internal_source_slot_id(mime)
            tgt_path, side, _, swap_id = self._resolve_drop_target(
                event.position().toPoint(), internal=True
            )
            self.state.drag_internal = False
            self.state.drag_source_slot_id = None
            self.gl_grid.set_drag_state(False, None, None, False, None)
            if source_id is not None and side is not None:
                self._apply_internal_drop(source_id, tgt_path, side, swap_id)
            event.acceptProposedAction()
            return

        tgt_path, side, root_tgt, _ = self._resolve_drop_target(
            event.position().toPoint(), internal=False
        )
        self.gl_grid.set_drag_state(False, None, None, False, None)
        paths = []
        for url in mime.urls():
            path = Path(url.toLocalFile())
            if path.is_file() and path.suffix.lower() in _IMAGE_EXTENSIONS:
                paths.append(path)
        if paths:
            self.images_dropped.emit(paths, (tgt_path, root_tgt), side)
            event.acceptProposedAction()

    def _apply_internal_drop(
        self,
        source_id: int,
        target_path: tuple[int, ...] | None,
        side: str,
        swap_slot_id: int | None,
    ) -> None:
        if side == "center" and swap_slot_id is not None and swap_slot_id != source_id:
            self.state.root = swap_slot_ids(self.state.root, source_id, swap_slot_id)
        elif target_path is not None:
            # Move: prune source first, then re-resolve a stable path for the
            # target by slot_id (paths shift after prune; we anchor on the first
            # leaf in the original target subtree).
            anchor_slot = self._anchor_slot_for_path(target_path)
            if anchor_slot is None or anchor_slot == source_id:
                return
            pruned = remove_leaf(self.state.root, source_id)
            if pruned is None:
                self.state.root = LeafNode(source_id)
            else:
                # Re-find anchor in pruned tree; promote back up if its parent
                # split matches the original depth (keeps "row-level" intent).
                new_anchor_path = find_path(pruned, anchor_slot)
                if new_anchor_path is None:
                    self.state.root = pruned
                else:
                    # Promote to the same depth as the original target (so a
                    # split-level target stays split-level after prune).
                    target_depth = len(target_path)
                    new_path = tuple(new_anchor_path[:target_depth])
                    self.state.root = insert_beside_path(
                        pruned, new_path, side, source_id
                    )
        self.gl_grid.set_state(self.state)

    def _anchor_slot_for_path(self, path: tuple[int, ...]) -> int | None:
        """Return slot_id of the first leaf inside the subtree at `path`."""
        from tabs.multi_compare.models import leaves, node_at_path
        node = node_at_path(self.state.root, path)
        if node is None:
            return None
        first = leaves(node)
        return first[0].slot_id if first else None

    def keyPressEvent(self, event) -> None:
        self.gl_grid.keyPressEvent(event)
