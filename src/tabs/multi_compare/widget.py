"""Main widget for multi-compare tab — composes toolbar + GL grid + footer."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QDragEnterEvent, QDropEvent, QFont, QPainter, QPen
from PyQt6.QtWidgets import QVBoxLayout, QWidget

from tabs.multi_compare.models import CompareSlot, MultiCompareState
from tabs.multi_compare.ui.footer import MultiCompareFooter
from tabs.multi_compare.ui.gl_grid import GLGridWidget
from tabs.multi_compare.ui.toolbar import MultiCompareToolbar

if TYPE_CHECKING:
    import numpy as np

_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp"}

class MultiCompareWidget(QWidget):
    """Composite widget: toolbar + GL grid + footer with drop hint overlay."""

    images_dropped = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.state = MultiCompareState()

        self.setAcceptDrops(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(400, 300)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.toolbar = MultiCompareToolbar(self)
        self.gl_grid = GLGridWidget(self)
        self.footer = MultiCompareFooter(self)

        layout.addWidget(self.toolbar)
        layout.addWidget(self.gl_grid, 1)
        layout.addWidget(self.footer)

        self.toolbar.reset_zoom_clicked.connect(self._on_reset_zoom)
        self.toolbar.toggle_grid_clicked.connect(self._on_toggle_grid)
        self.toolbar.clear_clicked.connect(self._on_clear)

    def set_state(self, state: MultiCompareState) -> None:
        self.state = state
        self.gl_grid.set_state(state)
        self.toolbar.update_slot_count(len(state.slots))
        self._update_empty_hint_visibility()

    def add_image(self, path: Path, image: "np.ndarray", label: str = "") -> int:
        slot_id = len(self.state.slots)
        slot = CompareSlot(id=slot_id, path=path, label=label or path.stem, image=image)
        self.state.slots.append(slot)
        self.gl_grid.set_state(self.state)
        self.toolbar.update_slot_count(len(self.state.slots))
        self._update_empty_hint_visibility()
        return slot_id

    def remove_slot(self, slot_id: int) -> None:
        self.state.slots = [s for s in self.state.slots if s.id != slot_id]
        if self.state.focused_slot_id == slot_id:
            self.state.focused_slot_id = None
        self.gl_grid.set_state(self.state)
        self.toolbar.update_slot_count(len(self.state.slots))
        self._update_empty_hint_visibility()

    def focus_slot(self, slot_id: int | None) -> None:
        self.state.focused_slot_id = slot_id
        self.gl_grid.set_state(self.state)

    def reset_view(self) -> None:
        self.state.zoom = 1.0
        self.state.pan_x = 0.0
        self.state.pan_y = 0.0
        self.gl_grid.set_state(self.state)

    def _on_reset_zoom(self) -> None:
        self.reset_view()

    def _on_toggle_grid(self) -> None:
        if self.state.is_focused:
            self.focus_slot(None)

    def _on_clear(self) -> None:
        self.state = MultiCompareState()
        self.gl_grid.set_state(self.state)
        self.toolbar.update_slot_count(0)
        self._update_empty_hint_visibility()

    def _update_empty_hint_visibility(self) -> None:
        has_images = len(self.state.slots) > 0
        self.toolbar.setVisible(has_images)
        self.footer.setVisible(has_images)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        paths = []
        for url in event.mimeData().urls():
            path = Path(url.toLocalFile())
            if path.is_file() and path.suffix.lower() in _IMAGE_EXTENSIONS:
                paths.append(path)
        if paths:
            self.images_dropped.emit(paths)
            event.acceptProposedAction()

    def keyPressEvent(self, event) -> None:
        self.gl_grid.keyPressEvent(event)
