"""Multi-compare split dividers are explicit overlays, not incidental gaps."""

import numpy as np
from PySide6.QtCore import QRect
from PySide6.QtGui import QColor, QPalette

from tabs.multi_compare.models import (
    CompareSlot,
    LeafNode,
    MultiCompareState,
    SplitNode,
)
from tabs.multi_compare.scene.overlay_painter import MultiCompareOverlayPainter
from tabs.multi_compare.scene.passes.dividers import DividersOverlaySource
from tabs.multi_compare.services.composition_builder import build_composition_plan
from ui.canvas_presentation.composition import resolve_composition


class _Host:
    def __init__(self, state):
        self.state = state
        self._palette = QPalette()
        self._palette.setColor(QPalette.ColorRole.Mid, QColor(120, 130, 140))

    def palette(self):
        return self._palette

    def devicePixelRatioF(self):
        return 1.0


def _state():
    image = np.zeros((100, 100, 3), dtype=np.uint8)
    return MultiCompareState(
        slots=[
            CompareSlot(id=1, label="", image=image),
            CompareSlot(id=2, label="", image=image),
        ],
        root=SplitNode("h", [LeafNode(1), LeafNode(2)], [1.0, 1.0]),
    )


def test_divider_overlay_paints_even_without_labels_or_drag(qapp):
    state = _state()
    composition = resolve_composition(
        build_composition_plan(state, include_labels=False)
    )

    image = MultiCompareOverlayPainter(_Host(state)).build(
        composition,
        0.25,
        0.0,
        0.0,
        100,
        100,
    )

    assert image is not None
    assert not image.isNull()


def test_divider_projection_uses_minimum_framebuffer_thickness():
    source = DividersOverlaySource()
    rect = source._project_gap(
        "h",
        QRect(40, 0, 4, 200),
        0.25,
        (0.0, 0.0),
    )

    assert rect.width() == source.MIN_THICKNESS_FB
