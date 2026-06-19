"""Multi Compare export stays tab-owned and saves the selected output format."""

from pathlib import Path
from types import SimpleNamespace

import numpy as np
from PIL import Image
from PyQt6.QtCore import QRect
from PyQt6.QtGui import QColor, QImage, QPainter

from tabs.multi_compare.controller import MultiCompareController
from tabs.multi_compare.models import CompareSlot, LeafNode
from tabs.multi_compare.services.image_export import save_composite


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


def _controller_for_painting():
    controller = MultiCompareController.__new__(MultiCompareController)
    controller.widget = SimpleNamespace(
        gl_grid=SimpleNamespace(
            LABEL_PADDING=6,
            LABEL_BG_ALPHA=170,
            LABEL_FONT_PT=10,
        )
    )
    return controller


def test_multi_compare_export_matches_live_letterbox_and_zoom_transform():
    controller = _controller_for_painting()
    source = np.zeros((20, 40, 3), dtype=np.uint8)
    source[:, :20] = (255, 0, 0)
    source[:, 20:] = (0, 0, 255)

    fit_output = QImage(100, 100, QImage.Format.Format_RGBA8888)
    fit_output.fill(QColor(0, 0, 0, 0))
    painter = QPainter(fit_output)
    controller._paint_slot_image(
        painter,
        QRect(0, 0, 100, 100),
        source,
        zoom=1.0,
        pan_x=0.0,
        pan_y=0.0,
    )
    painter.end()

    assert fit_output.pixelColor(50, 10) == QColor(0, 0, 0, 255)
    assert fit_output.pixelColor(20, 50).red() > 200
    assert fit_output.pixelColor(80, 50).blue() > 200

    zoom_output = QImage(100, 100, QImage.Format.Format_RGBA8888)
    zoom_output.fill(QColor(0, 0, 0, 0))
    painter = QPainter(zoom_output)
    controller._paint_slot_image(
        painter,
        QRect(0, 0, 100, 100),
        source,
        zoom=2.0,
        pan_x=0.2,
        pan_y=0.0,
    )
    painter.end()

    assert zoom_output.pixelColor(10, 50).red() > 200
    assert zoom_output.pixelColor(70, 50).red() > 200
    assert zoom_output.pixelColor(95, 50).blue() > 200


def test_multi_compare_export_uses_focused_slot_as_full_frame():
    controller = MultiCompareController.__new__(MultiCompareController)
    focused_image = np.zeros((20, 20, 3), dtype=np.uint8)
    focused_image[:] = (0, 255, 0)
    hidden_image = np.zeros((20, 20, 3), dtype=np.uint8)
    hidden_image[:] = (255, 0, 0)
    controller.widget = SimpleNamespace(
        state=SimpleNamespace(
            slots=[
                CompareSlot(id=7, image=focused_image),
                CompareSlot(id=8, image=hidden_image),
            ],
            root=LeafNode(8),
            is_focused=True,
            focused_slot_id=7,
            zoom=1.0,
            pan_x=0.0,
            pan_y=0.0,
        ),
        gl_grid=SimpleNamespace(
            width=lambda: 640,
            height=lambda: 360,
            CELL_GAP=4,
            LABEL_PADDING=6,
            LABEL_BG_ALPHA=170,
            LABEL_FONT_PT=10,
        ),
    )

    output = controller._compose_image(640, 360)

    center = output.pixelColor(320, 180)
    assert center.green() > 200
    assert center.red() < 50
