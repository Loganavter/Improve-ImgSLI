import numpy as np
import pytest
from PIL import Image
from PySide6.QtGui import QImage

from engine.store.pyramid_pixel_store import (
    COARSEST_MIN_DIM,
    PyramidPixelStore,
    _halve_box_filter,
)
from engine.store.tiled_pixel_store import TiledPixelStore


def _noise_store(width, height, seed=7):
    rng = np.random.default_rng(seed)
    arr = rng.integers(0, 256, size=(height, width, 4), dtype=np.uint8)
    arr[:, :, 3] = 255
    return TiledPixelStore.from_pil(Image.fromarray(arr, mode="RGBA")), arr


def test_halve_box_filter_even():
    arr = np.arange(4 * 4 * 4, dtype=np.uint8).reshape(4, 4, 4)
    out = _halve_box_filter(arr)
    assert out.shape == (2, 2, 4)
    expected = (
        arr.astype(np.uint16)[0::2, 0::2]
        + arr.astype(np.uint16)[1::2, 0::2]
        + arr.astype(np.uint16)[0::2, 1::2]
        + arr.astype(np.uint16)[1::2, 1::2]
        + 2
    ) >> 2
    assert np.array_equal(out, expected.astype(np.uint8))


def test_halve_box_filter_odd_dims_edge_padded():
    arr = np.full((3, 5, 4), 100, dtype=np.uint8)
    out = _halve_box_filter(arr)
    assert out.shape == (2, 3, 4)
    assert np.all(out == 100)


def test_build_levels_until_coarsest():
    store, _ = _noise_store(4096, 2048)
    pyramid = PyramidPixelStore.build_from(store)
    # 4096x2048 -> 2048x1024: min dim already <= COARSEST_MIN_DIM after one level.
    assert pyramid.level_count == 2
    assert pyramid.level(1).size == (2048, 1024)
    assert pyramid.is_complete()
    assert min(pyramid.level(pyramid.level_count - 1).size) <= COARSEST_MIN_DIM
    pyramid.close()
    assert pyramid.level_count == 1
    assert store.is_open
    store.close()


def test_ceil_halving_odd_dimensions():
    store, _ = _noise_store(2049, 1035)
    pyramid = PyramidPixelStore.build_from(store)
    assert pyramid.level(1).size == (1025, 518)
    pyramid.close()
    store.close()


def test_level_pixels_match_reference_downscale():
    store, arr = _noise_store(1030, 1029)
    pyramid = PyramidPixelStore.build_from(store)
    assert pyramid.level_count == 2
    level1 = np.asarray(pyramid.level(1).crop((0, 0, 515, 515)))
    assert np.array_equal(level1, _halve_box_filter(arr))
    pyramid.close()
    store.close()


def test_strip_seams_do_not_corrupt_output():
    # Height above build strip size forces multiple strips.
    store, arr = _noise_store(2048, 3000)
    pyramid = PyramidPixelStore(store)
    assert pyramid.build_next_level()
    level1 = np.asarray(pyramid.level(1).crop((0, 0, 1024, 1500)))
    assert np.array_equal(level1, _halve_box_filter(arr))
    pyramid.close()
    store.close()


def test_abort_discards_partial_level():
    store, _ = _noise_store(2048, 2048)
    pyramid = PyramidPixelStore(store)
    assert pyramid.build_next_level(should_abort=lambda: True) is False
    assert pyramid.level_count == 1
    store.close()


def test_closed_base_invalidates_build():
    store, _ = _noise_store(2048, 2048)
    pyramid = PyramidPixelStore(store)
    store.close()
    assert not pyramid.valid
    assert pyramid.build_next_level() is False
    assert pyramid.level_count == 1


def test_best_level_for_scale_clamps_to_built_levels():
    store, _ = _noise_store(4096, 4096)
    pyramid = PyramidPixelStore(store)
    assert pyramid.best_level_for_scale(0.01) == 0
    pyramid.build_all()
    assert pyramid.level_count == 3
    assert pyramid.best_level_for_scale(0.01) == 2
    assert pyramid.best_level_for_scale(1.0) == 0
    pyramid.close()
    store.close()


# --- Wave-A1 seam regression tests (identity, not presence) ---


def _qimage_array(img: QImage) -> np.ndarray:
    rgba = (
        img
        if img.format() == QImage.Format.Format_RGBA8888
        else img.convertToFormat(QImage.Format.Format_RGBA8888)
    )
    w, h = rgba.width(), rgba.height()
    raw = bytes(rgba.constBits())
    row_w = rgba.bytesPerLine() // 4
    return np.array(
        np.frombuffer(raw, dtype=np.uint8).reshape(h, row_w, 4)[:, :w, :],
        copy=True,
    )


def _level_qimage(level: TiledPixelStore, box: tuple[int, int, int, int]) -> QImage:
    from engine.store.tiled_pixel_store import qimage_from_pixel_source

    return qimage_from_pixel_source(level, box)


def _quadrant_store(size: int = 2048):
    arr = np.zeros((size, size, 4), dtype=np.uint8)
    half = size // 2
    arr[:, :, 3] = 255
    arr[:half, :half, 0] = 255  # top-left red
    arr[:half, half:, 1] = 255  # top-right green
    arr[half:, :half, 2] = 255  # bottom-left blue
    arr[half:, half:, :3] = 255  # bottom-right white
    return TiledPixelStore.from_pil(Image.fromarray(arr, mode="RGBA")), arr


def test_best_pixels_returns_exact_level_content():
    store, _ = _quadrant_store()
    pyramid = PyramidPixelStore.build_from(store)
    assert pyramid.level_count == 2
    # L0: rect inside the red quadrant must come back all red.
    got = pyramid.best_pixels((0, 0, 256, 256), 1.0)
    assert got is not None
    assert np.all(_qimage_array(got) == (255, 0, 0, 255))
    expected = _level_qimage(pyramid.level(0), (0, 0, 256, 256))
    assert np.array_equal(_qimage_array(got), _qimage_array(expected))
    # L1: same L0 rect mapped to level coords must equal the level store.
    got1 = pyramid.best_pixels((0, 0, 256, 256), 0.5)
    assert got1 is not None
    assert (got1.width(), got1.height()) == (128, 128)
    expected1 = _level_qimage(pyramid.level(1), (0, 0, 128, 128))
    assert np.array_equal(_qimage_array(got1), _qimage_array(expected1))
    pyramid.close()
    store.close()


def test_best_pixels_distinct_rects_distinct_content():
    store, _ = _noise_store(2048, 2048)
    pyramid = PyramidPixelStore.build_from(store)
    red_zone = pyramid.best_pixels((0, 0, 128, 128), 1.0)
    far_zone = pyramid.best_pixels((1024, 1024, 1152, 1152), 1.0)
    assert red_zone is not None and far_zone is not None
    # payload(rect) == content(rect): different rects, different bytes.
    assert not np.array_equal(_qimage_array(red_zone), _qimage_array(far_zone))
    # Same rect twice: identical bytes.
    again = pyramid.best_pixels((0, 0, 128, 128), 1.0)
    assert np.array_equal(_qimage_array(red_zone), _qimage_array(again))
    pyramid.close()
    store.close()


def test_best_pixels_gap_on_invalid_rect_and_scale():
    store, _ = _noise_store(2048, 2048)
    pyramid = PyramidPixelStore.build_from(store)
    assert pyramid.best_pixels((10, 10, 10, 10), 1.0) is None  # empty
    assert pyramid.best_pixels((20, 20, 10, 10), 1.0) is None  # reversed
    assert pyramid.best_pixels((0, 0, 64), 1.0) is None  # wrong arity
    assert pyramid.best_pixels("0123", 1.0) is None  # non-numeric
    assert pyramid.best_pixels((0.5, 0, 64, 64), 1.0) is None  # float
    assert pyramid.best_pixels((5000, 5000, 5100, 5100), 1.0) is None  # outside
    assert pyramid.best_pixels((-100, -100, -10, -10), 1.0) is None  # outside
    assert pyramid.best_pixels((0, 0, 64, 64), "close") is None  # bad scale
    assert pyramid.best_pixels(None, 1.0) is None
    store.close()  # stale pyramid fails closed, not to neighbor bytes
    assert pyramid.best_pixels((0, 0, 64, 64), 1.0) is None


def test_best_pixels_unbuilt_level_is_gap_not_neighbor_bytes():
    store, _ = _noise_store(2048, 2048)
    pyramid = PyramidPixelStore.build_from(store)
    assert pyramid.is_level_built(1)
    pyramid.level(1).close()  # selected level unreadable, L0 still alive
    assert not pyramid.is_level_built(1)
    assert pyramid.level_if_built(1) is None
    # Scale 0.5 selects level 1: must be a gap, never L0's bytes.
    assert pyramid.best_pixels((0, 0, 256, 256), 0.5) is None
    # L0 path still serves its own level.
    assert pyramid.best_pixels((0, 0, 256, 256), 1.0) is not None
    pyramid.close()
    store.close()


def test_best_pixels_zoom_remap_no_cross_binding():
    store, _ = _noise_store(2048, 2048)
    pyramid = PyramidPixelStore.build_from(store)
    rect = (512, 512, 768, 768)
    wide = pyramid.best_pixels(rect, 1.0)
    coarse = pyramid.best_pixels(rect, 0.5)
    assert wide is not None and coarse is not None
    assert (wide.width(), wide.height()) == (256, 256)
    assert (coarse.width(), coarse.height()) == (128, 128)
    # Each zoom binds its own level's bytes — no cross-binding on switch.
    assert np.array_equal(
        _qimage_array(wide), _qimage_array(_level_qimage(pyramid.level(0), rect))
    )
    assert np.array_equal(
        _qimage_array(coarse),
        _qimage_array(_level_qimage(pyramid.level(1), (256, 256, 384, 384))),
    )
    pyramid.close()
    store.close()


def test_level_if_built_sampler_idiom_never_raises():
    store, _ = _noise_store(2048, 2048)
    pyramid = PyramidPixelStore.build_from(store)
    assert pyramid.level_if_built(0) is store
    assert pyramid.level_if_built(1) is pyramid.level(1)
    assert pyramid.is_level_built(0) and pyramid.is_level_built(1)
    for bad in (-1, 2, 99, "1", 1.0, None, True, (0,)):
        assert pyramid.level_if_built(bad) is None
        assert pyramid.is_level_built(bad) is False
    pyramid.close()
    store.close()


def test_generation_snapshot_stale_guard():
    store, _ = _noise_store(2048, 2048)
    pyramid = PyramidPixelStore(store)
    assert pyramid.generation == store.generation
    token = pyramid.generation
    store.close()  # reunify/close bumps the base generation
    assert pyramid.generation == token  # snapshot, not live
    assert pyramid.generation != store.generation
    assert not pyramid.valid
    assert pyramid.best_pixels((0, 0, 64, 64), 1.0) is None


def test_coarse_factory_scaled_read_without_full_frame(tmp_path, monkeypatch):
    import engine.store.tiled_pixel_store as tps_module

    materialize_calls: list = []
    real_materialize = TiledPixelStore.materialize_full
    real_to_real = tps_module.to_real_pil_copy

    def _spy_materialize(self):
        materialize_calls.append(self)
        return real_materialize(self)

    def _spy_to_real(image):
        materialize_calls.append(image)
        return real_to_real(image)

    monkeypatch.setattr(TiledPixelStore, "materialize_full", _spy_materialize)
    monkeypatch.setattr(tps_module, "to_real_pil_copy", _spy_to_real)
    # This test covers the bounded-reader (PIL) branch: force it even where
    # libvips is installed (there PNG/JPEG would stream via vips with a
    # different downscale kernel, breaking the PIL-identity assert below).
    # The vips branch has its own coverage further down this file.
    monkeypatch.setattr(
        "shared.image_processing.progressive_loader.pyvips_can_stream",
        lambda path: False,
    )

    rng = np.random.default_rng(11)
    arr = rng.integers(0, 256, size=(1536, 2048, 4), dtype=np.uint8)
    arr[:, :, 3] = 255
    src = tmp_path / "large.png"
    Image.fromarray(arr, mode="RGBA").save(src)

    coarse = PyramidPixelStore.coarse_from_source(
        str(src), long_edge=512, tmp_dir=str(tmp_path)
    )
    try:
        assert coarse is not None
        assert materialize_calls == []  # no full-frame materialization
        assert coarse.size == (512, 384)
        ref = Image.open(src)
        ref.thumbnail((512, 512), Image.Resampling.BILINEAR)
        ref = ref.convert("RGBA")
        got = np.asarray(coarse.crop((0, 0, 512, 384)))
        assert np.array_equal(got, np.asarray(ref))
    finally:
        if coarse is not None:
            coarse.close()
    assert PyramidPixelStore.coarse_from_source(
        str(tmp_path / "missing.png"), tmp_dir=str(tmp_path)
    ) is None
    assert PyramidPixelStore.coarse_from_source(
        str(src), long_edge="wide", tmp_dir=str(tmp_path)
    ) is None


# --- Wave-B1 roughness R1: vips-branch coverage (real pyvips) ---
#
# These tests exercise ``_coarse_from_source_vips`` + the streamable path of
# ``coarse_from_source`` with real files. They degrade via
# ``pytest.importorskip("pyvips")`` so CI without libvips still runs the file.
# Identity asserts (dims + content vs an independent PIL downscale), not sizes
# alone; vips and PIL use different kernels, so content comparisons carry an
# explicit tolerance instead of byte equality.


def _quadrant_file(path, width=2048, height=1536, fmt="JPEG", exif_orientation=None):
    """Save a 4-block RGB file (red/green/blue/white quadrants); returns path."""
    half_w, half_h = width // 2, height // 2
    arr = np.zeros((height, width, 3), dtype=np.uint8)
    arr[:half_h, :half_w] = (255, 0, 0)
    arr[:half_h, half_w:] = (0, 255, 0)
    arr[half_h:, :half_w] = (0, 0, 255)
    arr[half_h:, half_w:] = (255, 255, 255)
    img = Image.fromarray(arr, mode="RGB")
    kwargs = {}
    if exif_orientation is not None:
        exif = Image.Exif()
        exif[0x0112] = int(exif_orientation)
        kwargs["exif"] = exif
    img.save(path, fmt, **kwargs)
    return path


def _quadrant_centers(shape):
    """Interior sample points (y, x) of the four downscaled quadrant blocks."""
    h, w = shape[:2]
    return [(h // 4, w // 4), (h // 4, 3 * w // 4), (3 * h // 4, w // 4), (3 * h // 4, 3 * w // 4)]


def _assert_quadrant_colors(rgb, jpeg=True):
    """Quadrant interiors keep their block colors (red/green/blue/white)."""
    lo, hi = (150, 110) if jpeg else (200, 60)
    (r_y, r_x), (g_y, g_x), (b_y, b_x), (w_y, w_x) = _quadrant_centers(rgb.shape)
    assert rgb[r_y, r_x, 0] > lo and rgb[r_y, r_x, 1] < hi and rgb[r_y, r_x, 2] < hi
    assert rgb[g_y, g_x, 1] > lo and rgb[g_y, g_x, 0] < hi and rgb[g_y, g_x, 2] < hi
    assert rgb[b_y, b_x, 2] > lo and rgb[b_y, b_x, 0] < hi and rgb[b_y, b_x, 1] < hi
    assert bool(np.all(rgb[w_y, w_x] > lo))


def test_coarse_vips_jpeg_dims_content_and_failure_path(tmp_path):
    pytest.importorskip("pyvips")
    from shared.image_processing.progressive_loader import pyvips_can_stream

    src = _quadrant_file(tmp_path / "large.jpg")
    if not pyvips_can_stream(str(src)):
        pytest.skip("libvips cannot stream JPEG in this build")
    cap = 512
    coarse = PyramidPixelStore.coarse_from_source(
        str(src), long_edge=cap, tmp_dir=str(tmp_path)
    )
    try:
        assert coarse is not None
        assert coarse.is_open
        assert coarse.size == (512, 384)  # long edge capped
        got = np.asarray(coarse.crop((0, 0, 512, 384)))
        assert got.shape == (384, 512, 4)  # RGBA bytes, strip-written store valid
        assert np.all(got[:, :, 3] == 255)
        _assert_quadrant_colors(got[:, :, :3], jpeg=True)
        # Independent reference: PIL LANCZOS downscale of the same file.
        with Image.open(src) as ref_img:
            ref = np.asarray(
                ref_img.convert("RGB").resize((512, 384), Image.Resampling.LANCZOS)
            )
        mean_abs = np.mean(
            np.abs(got[:, :, :3].astype(np.int16) - ref.astype(np.int16))
        )
        assert mean_abs < 8.0
    finally:
        if coarse is not None:
            coarse.close()
    # Failure path fails closed to None (streamable ext, so the vips branch).
    corrupt = tmp_path / "corrupt.jpg"
    corrupt.write_bytes(b"\x00\x11not-a-jpeg" * 64)
    assert PyramidPixelStore.coarse_from_source(
        str(corrupt), tmp_dir=str(tmp_path)
    ) is None
    assert PyramidPixelStore.coarse_from_source(
        str(tmp_path / "missing.jpg"), tmp_dir=str(tmp_path)
    ) is None


def test_coarse_vips_png_rgba(tmp_path):
    pytest.importorskip("pyvips")
    from shared.image_processing.progressive_loader import pyvips_can_stream

    half_w, half_h, w, h = 1024, 768, 2048, 1536
    arr = np.zeros((h, w, 4), dtype=np.uint8)
    arr[:, :, 3] = 255
    arr[:half_h, :half_w, 0] = 255
    arr[:half_h, half_w:, 1] = 255
    arr[half_h:, :half_w, 2] = 255
    arr[half_h:, half_w:, :3] = 255
    src = tmp_path / "large.png"
    Image.fromarray(arr, mode="RGBA").save(src)
    if not pyvips_can_stream(str(src)):
        pytest.skip("libvips cannot stream PNG in this build")
    coarse = PyramidPixelStore.coarse_from_source(
        str(src), long_edge=512, tmp_dir=str(tmp_path)
    )
    try:
        assert coarse is not None
        assert coarse.size == (512, 384)
        got = np.asarray(coarse.crop((0, 0, 512, 384)))
        assert got.shape == (384, 512, 4)
        assert np.all(got[:, :, 3] == 255)
        _assert_quadrant_colors(got[:, :, :3], jpeg=False)
        with Image.open(src) as ref_img:
            ref = np.asarray(
                ref_img.convert("RGB").resize((512, 384), Image.Resampling.LANCZOS)
            )
        mean_abs = np.mean(
            np.abs(got[:, :, :3].astype(np.int16) - ref.astype(np.int16))
        )
        assert mean_abs < 5.0  # lossless source: tighter agreement
    finally:
        if coarse is not None:
            coarse.close()


def test_coarse_vips_direct_matches_dispatch(tmp_path):
    """``_coarse_from_source_vips`` direct call == dispatched streamable path."""
    pytest.importorskip("pyvips")
    from shared.image_processing.progressive_loader import pyvips_can_stream

    src = _quadrant_file(tmp_path / "direct.jpg")
    if not pyvips_can_stream(str(src)):
        pytest.skip("libvips cannot stream JPEG in this build")
    direct = PyramidPixelStore._coarse_from_source_vips(str(src), 512, str(tmp_path))
    dispatched = PyramidPixelStore.coarse_from_source(
        str(src), long_edge=512, tmp_dir=str(tmp_path)
    )
    try:
        assert direct is not None and dispatched is not None
        assert direct.size == dispatched.size == (512, 384)
        assert np.array_equal(
            np.asarray(direct.crop((0, 0, 512, 384))),
            np.asarray(dispatched.crop((0, 0, 512, 384))),
        )
    finally:
        direct.close()
        if dispatched is not None:
            dispatched.close()


# --- Wave-B1 roughness R2: EXIF-orientation parity (both branches unrotated) ---


def test_coarse_exif_orientation_parity_unrotated(tmp_path, monkeypatch):
    """EXIF orientation 6: vips branch, PIL branch, and legacy render agree.

    Nothing in the gallery thumb path transposes EXIF today, so both coarse
    branches must stay unrotated (``no_rotate`` on the vips call). A rotated
    render of this landscape file would come back portrait (384x512).
    """
    pytest.importorskip("pyvips")
    from shared.image_processing.progressive_loader import pyvips_can_stream

    src = _quadrant_file(tmp_path / "exif6.jpg", 1600, 1200, "JPEG", exif_orientation=6)
    if not pyvips_can_stream(str(src)):
        pytest.skip("libvips cannot stream JPEG in this build")
    cap = 512
    # Legacy reference: the exact PIL-branch recipe (no exif_transpose).
    with Image.open(src) as probe:
        legacy = probe.copy()
        legacy.thumbnail((cap, cap), Image.Resampling.BILINEAR)
        legacy = legacy.convert("RGBA")
    assert legacy.size == (512, 384)  # unrotated landscape stays landscape
    legacy_arr = np.asarray(legacy)
    # PIL branch (forced): byte-identical to the legacy render.
    monkeypatch.setattr(
        "shared.image_processing.progressive_loader.pyvips_can_stream",
        lambda path: False,
    )
    pil_coarse = PyramidPixelStore.coarse_from_source(
        str(src), long_edge=cap, tmp_dir=str(tmp_path)
    )
    try:
        assert pil_coarse is not None
        assert pil_coarse.size == (512, 384)
        assert np.array_equal(
            np.asarray(pil_coarse.crop((0, 0, 512, 384))), legacy_arr
        )
    finally:
        if pil_coarse is not None:
            pil_coarse.close()
    # Vips branch (direct): identical orientation — also unrotated landscape.
    vips_coarse = PyramidPixelStore._coarse_from_source_vips(
        str(src), cap, str(tmp_path)
    )
    try:
        assert vips_coarse.size == (512, 384)  # portrait here == auto-rotated
        vips_arr = np.asarray(vips_coarse.crop((0, 0, 512, 384)))
        assert vips_arr.shape == (384, 512, 4)
        _assert_quadrant_colors(vips_arr[:, :, :3], jpeg=True)
        mean_abs = np.mean(
            np.abs(vips_arr[:, :, :3].astype(np.int16) - legacy_arr[:, :, :3].astype(np.int16))
        )
        assert mean_abs < 10.0
    finally:
        vips_coarse.close()