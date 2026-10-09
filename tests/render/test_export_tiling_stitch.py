"""TiledFramebufferExporter stitches tile grabs into one image."""

from PIL import Image
from PySide6.QtGui import QColor, QImage

from engine.gpu.export_tiling import TiledFramebufferExporter, iter_export_tile_rects


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
            # Encode the tile's own origin so the stitched pixel is falsifiable:
            # /100 keeps distinct tiles distinct (left%250 collided: 0/3000/6000).
            qimg.fill(QColor(((left // 100) % 250) + 1, ((top // 100) % 250) + 1, 128, 255))
        return qimg


def _expected_origin_color(left: int, top: int) -> tuple[int, int, int, int]:
    return (((left // 100) % 250) + 1, ((top // 100) % 250) + 1, 128, 255)


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

    # Content identity per tile: each tile's pixels must land in that tile's own
    # region. The stub encodes the tile origin in RGB, so sampling the centre of
    # each expected tile rect must reproduce that tile's colour — a swapped,
    # duplicated, or mis-offset paste fails here. (Alpha-only assertions did not.)
    rects = list(iter_export_tile_rects(9000, 100, 4096))
    assert len(rects) >= 2
    for left, top, w, h in rects:
        cx, cy = left + w // 2, top + h // 2
        assert image.getpixel((cx, cy)) == _expected_origin_color(left, top), (left, top)

    assert image.getpixel((0, 0)) == _expected_origin_color(0, 0)
    assert viewports[-1] is None
