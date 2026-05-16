"""Controller for multi-compare tab — loads images, manages state."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np

from tabs.multi_compare.models import MultiCompareState
from tabs.multi_compare.widget import MultiCompareWidget

logger = logging.getLogger("ImproveImgSLI")

class MultiCompareController:
    """Manages image loading and state for the multi-compare widget."""

    def __init__(self, widget: MultiCompareWidget, store: Any = None):
        self.widget = widget
        self.store = store
        self.state = MultiCompareState()

        self.widget.images_dropped.connect(self._on_images_dropped)
        self.widget.set_state(self.state)

    def load_images(self, paths: list[Path]) -> None:
        for path in paths:
            if len(self.state.slots) >= self.state.max_slots:
                logger.warning(
                    f"Max slots ({self.state.max_slots}) reached, skipping: {path.name}"
                )
                break
            self._load_single(path)
        self.widget.set_state(self.state)

    def clear(self) -> None:
        self.state = MultiCompareState()
        self.widget.set_state(self.state)

    def _on_images_dropped(self, paths: list) -> None:
        self.load_images([Path(p) if not isinstance(p, Path) else p for p in paths])

    def _load_single(self, path: Path) -> None:
        try:
            from PIL import Image

            img = Image.open(path)
            img = img.convert("RGB")
            arr = np.ascontiguousarray(np.array(img, dtype=np.uint8))
            self.widget.add_image(path, arr, label=path.stem)
        except Exception as e:
            logger.error(f"Failed to load {path}: {e}")
