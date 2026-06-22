"""Multi Compare export stays tab-owned and saves the selected output format."""

from pathlib import Path

import numpy as np
from PIL import Image
from PySide6.QtGui import QColor, QImage

from tabs.multi_compare.models import (
    CompareSlot,
    LeafNode,
    MultiCompareState,
    SplitNode,
)
from tabs.multi_compare.services.composition_builder import build_composition_plan
from tabs.multi_compare.services.image_export import save_composite
from ui.canvas_presentation.composition import (
    LayerNode,
    resolve_composition,
)


def test_multi_compare_export_saves_png(tmp_path):
    image = QImage(64, 32, QImage.Format.Format_RGBA8888)
    image.fill(QColor(12, 34, 56, 255))

    output = save_composite(
        image,
        {
            "output_dir": str(tmp_path),
            "file_name": "multi",
            "format": "PNG",
            "quality": 95,
            "background_color": (255, 255, 255, 255),
        },
    )

    assert Path(output).name == "multi.png"
    with Image.open(output) as saved:
        assert saved.size == (64, 32)
        assert saved.convert("RGB").getpixel((0, 0)) == (12, 34, 56)


def test_multi_compare_uses_host_export_dialog_service():
    controller_source = (
        Path(__file__).parents[2]
        / "src"
        / "tabs"
        / "multi_compare"
        / "controller.py"
    ).read_text(encoding="utf-8")
    tab_source = (
        Path(__file__).parents[2]
        / "src"
        / "tabs"
        / "multi_compare"
        / "tab.py"
    ).read_text(encoding="utf-8")

    assert "MultiCompareExportDialog" not in controller_source
    assert "plugins.export" not in controller_source
    assert "call_service(" in tab_source
    assert '"open_image_export_dialog"' in tab_source


def _slot(slot_id: int, w: int, h: int) -> CompareSlot:
    return CompareSlot(id=slot_id, image=np.zeros((h, w, 3), dtype=np.uint8))


def test_multi_compare_export_composition_carries_live_zoom_and_pan():
    """The composition plan is the contract between state and renderer:
    zoom/pan applied in the live widget must arrive on every layer node so
    any backend (current QRhi widget, future C++ renderer) produces the same
    transform.
    """
    state = MultiCompareState(
        root=SplitNode(
            direction="h",
            children=[LeafNode(slot_id=1), LeafNode(slot_id=2)],
            weights=[1.0, 1.0],
        ),
        slots=[_slot(1, 40, 20), _slot(2, 40, 20)],
        zoom=2.0,
        pan_x=0.2,
        pan_y=-0.05,
    )
    plan = build_composition_plan(state)
    resolved = resolve_composition(plan)
    assert len(resolved.layers) == 2
    for layer in resolved.layers:
        assert layer.zoom == 2.0
        assert layer.pan_x == 0.2
        assert layer.pan_y == -0.05


def test_multi_compare_export_uses_focused_slot_as_full_frame():
    """When a slot is focused, the composition collapses to a single layer
    covering the whole canvas. Other slots disappear from the render plan."""
    state = MultiCompareState(
        root=SplitNode(
            direction="h",
            children=[LeafNode(slot_id=7), LeafNode(slot_id=8)],
            weights=[1.0, 1.0],
        ),
        slots=[_slot(7, 20, 20), _slot(8, 40, 30)],
        focused_slot_id=7,
    )
    plan = build_composition_plan(state)
    assert isinstance(plan.root, LayerNode)
    assert plan.root.layer_id == 7
    resolved = resolve_composition(plan)
    assert len(resolved.layers) == 1
    assert resolved.layers[0].rect == (0, 0, plan.canvas_w, plan.canvas_h)
