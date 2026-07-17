"""Large-image SSIM must not materialize full TiledPixelStore."""

from PIL import Image

from shared.analysis.ssim_source import create_ssim_map_from_sources
from shared.image_processing.store_lease import StoreLease
from shared.image_processing.tiled_pixel_store import TiledPixelStore


def test_large_ssim_from_sources_avoids_materialize_full(monkeypatch):
    # 8192 is wide but only 64px tall — small enough for CI, still multi-tile.
    w, h = 8192, 64
    img1 = Image.new("RGBA", (w, h), (200, 10, 10, 255))
    img2 = Image.new("RGBA", (w, h), (200, 12, 10, 255))
    s1 = TiledPixelStore.from_pil(img1)
    s2 = TiledPixelStore.from_pil(img2)

    calls: list[str] = []

    def _spy_materialize_full():
        calls.append("materialize_full")
        raise AssertionError("materialize_full must not run")

    monkeypatch.setattr(s1, "materialize_full", _spy_materialize_full)
    monkeypatch.setattr(s2, "materialize_full", _spy_materialize_full)

    result = create_ssim_map_from_sources(
        s1,
        s2,
        lease1=StoreLease.capture(s1),
        lease2=StoreLease.capture(s2),
    )
    assert result is not None
    assert result.size == (w, h)
    assert calls == []

    if isinstance(result, TiledPixelStore):
        result.close()
    s1.close()
    s2.close()
