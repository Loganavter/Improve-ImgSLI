"""Lifecycle: load → unify → diff → export context → swap with store leases."""

from PIL import Image

from shared.analysis.diff_source import create_highlight_diff_from_sources
from shared.analysis.ssim_source import create_ssim_map_from_sources
from shared.image_processing.pixel_ops.downscale import downscale_pair_to_limit
from shared.image_processing.pixel_ops.unify import unify_pair
from shared.image_processing.store_lease import StoreLease
from shared.image_processing.tiled_pixel_store import (
    TiledPixelStore,
    qimage_from_pixel_source,
)
from tabs.image_compare.services.export_context_builder import ExportContextBuilder


def test_pipeline_survives_store_replacement():
    img1 = Image.new("RGBA", (128, 96), (255, 0, 0, 255))
    img2 = Image.new("RGBA", (96, 128), (0, 255, 0, 255))
    store1 = TiledPixelStore.from_pil(img1)
    store2 = TiledPixelStore.from_pil(img2)
    lease1 = StoreLease.capture(store1)
    lease2 = StoreLease.capture(store2)

    u1, u2 = unify_pair(store1, store2, lease1=lease1, lease2=lease2)
    assert u1 is not None and u2 is not None

    d1, d2 = downscale_pair_to_limit(u1, u2, 64)
    assert d1.size == d2.size

    qimage = qimage_from_pixel_source(u1)
    assert not qimage.isNull()

    ssim = create_ssim_map_from_sources(
        u1,
        u2,
        lease1=StoreLease.capture(u1),
        lease2=StoreLease.capture(u2),
    )
    assert ssim is not None

    highlight = create_highlight_diff_from_sources(
        u1,
        u2,
        lease1=StoreLease.capture(u1),
        lease2=StoreLease.capture(u2),
    )
    assert highlight is not None

    store1.close()
    store2.close()
    if isinstance(u1, TiledPixelStore):
        u1.close()
    if isinstance(u2, TiledPixelStore):
        u2.close()

    stale = unify_pair(store1, store2, lease1=lease1, lease2=lease2)
    assert stale == (None, None)


def test_export_preview_downscale_from_tiled_store():
    img1 = Image.new("RGBA", (320, 240), (40, 40, 40, 255))
    img2 = Image.new("RGBA", (280, 260), (50, 50, 50, 255))
    s1 = TiledPixelStore.from_pil(img1)
    s2 = TiledPixelStore.from_pil(img2)

    class _Store:
        viewport = type("VP", (), {})()

    builder = ExportContextBuilder(_Store(), gpu_export_service=None, state_coordinator=type("S", (), {})())
    preview1 = builder._downscale_for_preview(s1)
    preview2 = builder._downscale_for_preview(s2)
    assert preview1.size[0] <= 320 and preview2.size[0] <= 280

    s1.close()
    s2.close()
