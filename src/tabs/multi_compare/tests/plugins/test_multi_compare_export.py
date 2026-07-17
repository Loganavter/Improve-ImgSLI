"""Multi Compare export stays tab-owned and saves the selected output format."""

from pathlib import Path

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
from tabs.multi_compare.tests.pixel_fixtures import slot_image
from ui.canvas_presentation.composition import (
    LayerNode,
    resolve_composition,
)


def test_multi_compare_export_saves_png(tmp_path):
    qimage = QImage(64, 32, QImage.Format.Format_RGBA8888)
    qimage.fill(QColor(12, 34, 56, 255))
    # save_composite requires a plain PIL.Image (converted on the GUI thread
    # by the caller) — never pass a QImage, see image_export.py's docstring.
    ptr = qimage.constBits()
    image = Image.frombytes(
        "RGBA", (qimage.width(), qimage.height()), bytes(ptr)
    )

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
    tab_root = Path(__file__).parents[2]
    controller_source = (tab_root / "controller.py").read_text(encoding="utf-8")
    tab_source = (tab_root / "tab.py").read_text(encoding="utf-8")

    assert "MultiCompareExportDialog" not in controller_source
    assert "plugins.export" not in controller_source
    assert "call_service(" in tab_source
    assert '"open_image_export_dialog"' in tab_source


def _slot(slot_id: int, w: int, h: int) -> CompareSlot:
    return CompareSlot(id=slot_id, image=slot_image(w, h))


def test_multi_compare_quick_save_skips_export_dialog(monkeypatch, tmp_path):
    """Toolbar quick-save must write with last settings, never open the dialog."""
    from types import SimpleNamespace

    from tabs.multi_compare.controller import MultiCompareController

    dialog_calls: list = []
    saved: list = []

    widget = SimpleNamespace(
        state=SimpleNamespace(
            root=LeafNode(slot_id=1),
            slots=[_slot(1, 32, 24)],
        ),
        canvas=SimpleNamespace(width=lambda: 32, height=lambda: 24),
        images_dropped=SimpleNamespace(connect=lambda *_: None),
        add_requested=SimpleNamespace(connect=lambda *_: None),
        save_requested=SimpleNamespace(connect=lambda *_: None),
        quick_save_requested=SimpleNamespace(connect=lambda *_: None),
        settings_requested=SimpleNamespace(connect=lambda *_: None),
        help_requested=SimpleNamespace(connect=lambda *_: None),
        divider_color_picker_requested=SimpleNamespace(connect=lambda *_: None),
    )
    settings = SimpleNamespace(
        export_default_dir=str(tmp_path),
        export_use_default_dir=True,
        export_favorite_dir=None,
        export_last_format="PNG",
        export_quality=90,
        export_png_compress_level=6,
        export_png_optimize=True,
        export_fill_background=True,
        export_background_color=SimpleNamespace(r=1, g=2, b=3, a=255),
        export_comment_keep_default=False,
        export_comment_text="",
        export_resolution_scale=1.0,
    )
    store = SimpleNamespace(settings=settings)
    controller = MultiCompareController(
        widget,
        store=store,
        open_export_dialog=lambda **kwargs: dialog_calls.append(kwargs) or (0, {}),
    )
    monkeypatch.setattr(
        controller,
        "_native_canvas_size",
        lambda: (32, 24),
    )
    monkeypatch.setattr(
        controller,
        "_compose_image",
        lambda w, h, background_color=None, fill_background=True: QImage(
            w, h, QImage.Format.Format_RGBA8888
        ),
    )
    monkeypatch.setattr(
        "shared.image_processing.qt_conversion.qimage_to_pil",
        lambda _img: Image.new("RGBA", (32, 24), (1, 2, 3, 255)),
    )
    monkeypatch.setattr(
        controller,
        "_get_save_flow",
        lambda: SimpleNamespace(
            start_save_worker=lambda pil, opts: saved.append((pil, opts))
        ),
    )

    controller._on_quick_save_requested()

    assert dialog_calls == []
    assert len(saved) == 1
    _pil, options = saved[0]
    assert options["is_quick_save"] is True
    assert options["output_dir"] == str(tmp_path)
    assert options["format"] == "PNG"
    assert options["width"] == 32
    assert options["height"] == 24


def test_multi_compare_export_composition_carries_live_zoom_and_pan():
    """The composition plan is the contract between state and renderer:
    zoom/pan applied in the live widget must arrive on every layer node so
    the QRhi path produces a stable transform from state alone.
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
