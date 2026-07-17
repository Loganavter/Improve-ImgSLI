"""Tiled export geometry for multi-compare outputs."""

from shared.rendering.export_tiling import TiledFramebufferExporter, iter_export_tile_rects


def test_iter_export_tile_rects_splits_large_output():
    output_w, output_h = 9000, 5000
    max_extent = 4096

    rects = list(iter_export_tile_rects(output_w, output_h, max_extent))

    assert len(rects) > 1
    total_area = sum(w * h for _l, _t, w, h in rects)
    assert total_area == output_w * output_h
    assert max(left + w for left, _t, w, _h in rects) == output_w
    assert max(top + h for _l, top, _h, h in rects) == output_h


def test_mc_exporter_delegates_to_shared_tiler(monkeypatch):
    from types import SimpleNamespace

    from tabs.multi_compare.services import gpu_export as gpu_export_module

    captured = {}

    class _FakeExporter:
        def __init__(self, widget, **kwargs):
            captured["kwargs"] = kwargs
            self._last_size = None

        def render_rgba(self, canvas_w, canvas_h, *, max_extent=4096):
            captured["size"] = (canvas_w, canvas_h)
            captured["max_extent"] = max_extent
            from PIL import Image

            return Image.new("RGBA", (canvas_w, canvas_h), (9, 8, 7, 255))

    monkeypatch.setattr(gpu_export_module, "TiledFramebufferExporter", _FakeExporter)
    monkeypatch.setattr(
        "ui.widgets.canvas.rhi_backend.query_max_texture_size",
        lambda _rhi: 4096,
    )

    from tabs.multi_compare.services.gpu_export import MultiCompareGpuExporter
    from ui.canvas_presentation.composition import CompositionPlan, LayerNode

    exporter = MultiCompareGpuExporter()
    fake_widget = SimpleNamespace()
    fake_widget.rhi = lambda: object()
    monkeypatch.setattr(exporter, "_ensure_widget", lambda: fake_widget)

    composition = CompositionPlan(
        root=LayerNode(layer_id=1, image=None, zoom=1.0, pan_x=0.0, pan_y=0.0),
        canvas_w=9000,
        canvas_h=5000,
    )
    qimg = exporter.render_to_qimage(
        composition,
        output_w=9000,
        output_h=5000,
        background_color=None,
        fill_background=False,
    )
    assert captured["size"] == (9000, 5000)
    assert qimg.width() == 9000 and qimg.height() == 5000
