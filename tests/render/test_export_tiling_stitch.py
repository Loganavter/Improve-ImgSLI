"""TiledFramebufferExporter stitches tile grabs into one image."""

from PIL import Image
from PySide6.QtGui import QColor, QImage

from shared.rendering.export_tiling import TiledFramebufferExporter


class _StubWidget:
    def __init__(self):
        self._size = (0, 0)
        self.viewports: list[tuple[int, int, int, int] | None] = []
        self.prepare_calls = 0

    def resize(self, w, h):
        self._size = (int(w), int(h))

    def show(self):
        return None

    def update(self):
        return None

    def grabFramebuffer(self):
        w, h = self._size
        qimg = QImage(w, h, QImage.Format.Format_RGBA8888)
        vp = self.viewports[-1] if self.viewports else None
        if vp is None:
            qimg.fill(QColor(1, 2, 3, 255))
        else:
            _full_w, _full_h, left, top = vp
            qimg.fill(QColor((left % 250) + 1, (top % 250) + 1, 128, 255))
        return qimg


def test_tiled_framebuffer_exporter_stitches_large_canvas():
    widget = _StubWidget()
    viewports: list = []

    def set_viewport(vp):
        viewports.append(vp)
        widget.viewports.append(vp)

    def prepare():
        widget.prepare_calls += 1

    exporter = TiledFramebufferExporter(
        widget,
        set_export_viewport=set_viewport,
        prepare_frame=prepare,
        query_max_texture_size=lambda: 4096,
    )

    image = exporter.render_rgba(9000, 100, max_extent=4096)

    assert isinstance(image, Image.Image)
    assert image.size == (9000, 100)
    assert image.getpixel((0, 0))[3] == 255
    assert image.getpixel((5000, 50))[3] == 255
    assert len(viewports) >= 2
    assert viewports[-1] is None
