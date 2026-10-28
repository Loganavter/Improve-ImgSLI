"""Multi Compare export stays tab-owned and saves the selected output format."""

from pathlib import Path

from PIL import Image
from PySide6.QtGui import QColor, QImage

from tabs.multi_compare.models import (
    CompareSlot,
    LeafNode,
    MultiCompareDividerSettings,
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
    return CompareSlot(id=slot_id)


def _sources(*specs):
    return {sid: slot_image(w, h) for sid, w, h in specs}


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
        # Non-modal dialog service: returns the live dialog (None here), the
        # export would continue via its on_finished callback.
        open_export_dialog=lambda **kwargs: dialog_calls.append(kwargs) or None,
    )
    # B4: seed one cached tier so the tree is exportable (an imageless
    # tree must refuse — see test_multi_compare_quick_save_refuses_imageless_tree).
    widget.state.slots[0].path = Path("/fake/slot1.png")
    _seed = QImage(32, 24, QImage.Format.Format_RGBA8888)
    _seed.fill(QColor(9, 9, 9, 255))
    controller.pixel_cache.put_preview(widget.state.slots[0].path, _seed)
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


def test_multi_compare_quick_save_refuses_imageless_tree(monkeypatch, tmp_path):
    """B4: quick-save on a tree of imageless slots refuses — no blank write.

    Parity with IC ``ExportPresenter.quick_save`` (gated on
    ``ExportContextBuilder.has_images``): MC gates on
    ``has_exportable_pixels`` (same shared ``resolve_slot_source`` seam
    the menu/DnD paths use), so neither the save worker nor any file
    is produced.
    """
    from types import SimpleNamespace

    from tabs.multi_compare.controller import MultiCompareController
    from tabs.multi_compare.use_cases.export import has_exportable_pixels

    widget = SimpleNamespace(
        state=SimpleNamespace(
            root=LeafNode(slot_id=1),
            slots=[CompareSlot(id=1)],  # pathless → no cached tier possible
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
    controller = MultiCompareController(
        widget,
        store=SimpleNamespace(settings=settings),
        open_export_dialog=lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("dialog must not open on refusal")
        ),
    )
    assert has_exportable_pixels(controller) is False

    saved: list = []
    monkeypatch.setattr(
        controller,
        "_get_save_flow",
        lambda: SimpleNamespace(
            start_save_worker=lambda pil, opts: saved.append((pil, opts))
        ),
    )
    compose_calls: list = []
    monkeypatch.setattr(
        controller,
        "_compose_image",
        lambda w, h, background_color=None, fill_background=True: compose_calls.append(
            (w, h)
        )
        or QImage(w, h, QImage.Format.Format_RGBA8888),
    )

    controller._on_quick_save_requested()

    assert saved == []
    assert compose_calls == []
    assert list(tmp_path.iterdir()) == []


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
    plan = build_composition_plan(state, sources=_sources((7, 20, 20), (8, 40, 30)))
    assert isinstance(plan.root, LayerNode)
    assert plan.root.layer_id == 7
    resolved = resolve_composition(plan)
    assert len(resolved.layers) == 1
    assert resolved.layers[0].rect == (0, 0, plan.canvas_w, plan.canvas_h)

def test_multi_compare_native_canvas_leaves_no_letterbox_rim():
    """Export canvas must cover the images exactly, gaps included.

    The white rim the owner sees around a saved picture is the divider gap:
    the old native-size formula ignored it, so every cell was a few px short
    of the image aspect and the aspect-fit image left a transparent edge band
    that export fills white (default background / JPEG flatten). Red-before:
    this state produced canvas 2560x800 with 1278x800 cells and a 1 px rim.
    """
    from PIL import Image

    state = MultiCompareState(
        root=SplitNode(
            direction="h",
            children=[LeafNode(slot_id=1), LeafNode(slot_id=2)],
            weights=[1.0, 1.0],
        ),
        slots=[_slot(1, 1280, 800), _slot(2, 1280, 800)],
        divider_settings=MultiCompareDividerSettings(visible=True, thickness=4),
    )
    sources = {
        1: Image.new("RGBA", (1280, 800), (200, 40, 40, 255)),
        2: Image.new("RGBA", (1280, 800), (40, 200, 40, 255)),
    }

    plan = build_composition_plan(state, sources=sources)
    assert (plan.canvas_w, plan.canvas_h) == (2564, 800)
    assert [layer.rect for layer in resolve_composition(plan).layers] == [
        (0, 0, 1280, 800),
        (1284, 0, 1280, 800),
    ]
