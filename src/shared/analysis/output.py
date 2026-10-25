"""The single analysis-output boundary: numpy result -> PIL | TiledPixelStore.

Every analysis entry point (`differ`, `ssim_source`, `edge_detector`,
`channel_analyzer`, `diff_source`) finalizes its numpy result through
:func:`finalize_diff_output` instead of hand-rolling ``Image.fromarray``.
That centralizes the "small result stays in-memory, large result spills to
``TiledPixelStore``" decision in exactly one place, and lets the AST contract
test (``tests/contracts/test_analysis_output_boundary.py``) prove that no
analysis module constructs a full-frame PIL container directly.
"""

from __future__ import annotations

import logging

import numpy as np
from PIL import Image

from engine.store.tiled_pixel_store import TiledPixelStore
from core.log_names import APP_LOGGER_NAME

logger = logging.getLogger(APP_LOGGER_NAME)

DIFF_SPILL_MAX_DIMENSION = 4096
DIFF_SPILL_MAX_PIXELS = 16_000_000
_BLOCK = 512

_RGBA_MODES = {
    1: "L",
    3: "RGB",
}

_16BIT_MODES = ("I;16", "I;16B", "I;16L")


def to_u8_rgb(image: Image.Image) -> Image.Image:
    """PIL image -> 8-bit RGB with correct 16-bit scaling.

    16-bit inputs (``I;16`` family, e.g. 16-bit TIFF/JXL probes) scale
    0..65535 -> 0..255 via ``//257`` — never truncation (``astype(uint8)``
    mod-256: 300 -> 44) and never PIL's ``convert`` clip (300 -> 255).
    All other modes go through the plain ``convert("RGB")`` path.
    Lives here (not in differ/metrics) so the ``Image.fromarray``
    boundary contract keeps holding.
    """
    if image.mode in _16BIT_MODES:
        scaled = (np.asarray(image).astype(np.uint32) // 257).astype(np.uint8)
        return Image.fromarray(scaled, mode="L").convert("RGB")
    if image.mode == "RGB":
        return image
    return image.convert("RGB")


def to_u8_array(arr: np.ndarray) -> np.ndarray:
    """ndarray -> uint8 with the same 16-bit scaling (JXL uint16 probes).

    uint8 passes through; uint16 scales ``//257``; anything else clips
    and casts. Never bare ``astype(np.uint8)`` on >8-bit ints.
    """
    arr = np.asarray(arr)
    if arr.dtype == np.uint8:
        return arr
    if arr.dtype == np.uint16:
        return (arr.astype(np.uint32) // 257).astype(np.uint8)
    if arr.dtype.kind == "f":
        return np.clip(arr, 0.0, 255.0).astype(np.uint8)
    return np.clip(arr, 0, 255).astype(np.uint8)


def rgba_from_array(arr: np.ndarray) -> Image.Image:
    """Build an RGBA PIL from an (H, W, 4) uint8 array.

    Leaf helper for per-patch channel extraction (``extract_channel``): the
    caller owns a bounded region, so this never spills to a store and always
    returns PIL. Keeps every ``Image.fromarray`` inside this module.
    """
    return Image.fromarray(arr, mode="RGBA")


def finalize_diff_output(
    arr: np.ndarray,
    *,
    channels: int = 1,
) -> Image.Image | TiledPixelStore:
    """Return compact PIL for bounded results, else spill to ``TiledPixelStore``.

    ``channels`` is the numpy array's per-pixel channel count: ``1`` (gray,
    becomes L->RGBA) or ``3`` (RGB->RGBA).
    """
    if channels not in _RGBA_MODES:
        raise ValueError(f"Unsupported output channels: {channels}")
    mode = _RGBA_MODES[channels]
    height, width = arr.shape[:2]
    if (
        width * height <= DIFF_SPILL_MAX_PIXELS
        and max(width, height) <= DIFF_SPILL_MAX_DIMENSION
    ):
        return Image.fromarray(arr, mode=mode).convert("RGBA")

    store = TiledPixelStore.allocate(width, height)
    try:
        for oy in range(0, height, _BLOCK):
            oy1 = min(oy + _BLOCK, height)
            for ox in range(0, width, _BLOCK):
                ox1 = min(ox + _BLOCK, width)
                patch = arr[oy:oy1, ox:ox1]
                pil = Image.fromarray(patch, mode=mode).convert("RGBA")
                store.write_pil((ox, oy, ox1, oy1), pil)
        return store
    except OSError as exc:
        logger.warning("Diff spill to TiledPixelStore failed, keeping PIL: %s", exc)
        return Image.fromarray(arr, mode=mode).convert("RGBA")


def _spills(width: int, height: int) -> bool:
    """Same small-PIL / spill-to-store decision as ``finalize_diff_output``."""
    return not (
        width * height <= DIFF_SPILL_MAX_PIXELS
        and max(width, height) <= DIFF_SPILL_MAX_DIMENSION
    )


class StreamingDiffWriter:
    """Tile-streamed analysis output — bounded peak RAM, no full-frame result.

    The tiled producers (differ/ssim_source/diff_source) used to assemble a
    full-frame ``np.empty`` result before finalizing: peak RAM held the full
    input pair PLUS the full result (2-3x the frame). This writer takes one
    tile patch at a time via :meth:`write_tile`:

    - small results (within ``DIFF_SPILL_*`` limits) accumulate in one
      bounded RAM buffer (<= ``DIFF_SPILL_MAX_PIXELS`` px by construction)
      and finalize to PIL exactly like :func:`finalize_diff_output`;
    - large results preallocate the ``TiledPixelStore`` up front and spill
      each tile to disk as it arrives — peak RAM stays at tile scale no
      matter how large the frame.

    ``channels`` is the patch channel count (1 = gray, 3 = RGB), matching
    ``finalize_diff_output``. Patches are uint8 ndarrays shaped
    ``(h, w[, c])``; ``box`` is ``(left, top, right, bottom)`` in output
    pixels and must match the patch dims.
    """

    def __init__(self, width: int, height: int, *, channels: int):
        if channels not in _RGBA_MODES:
            raise ValueError(f"Unsupported output channels: {channels}")
        self._width = int(width)
        self._height = int(height)
        self._channels = int(channels)
        self._mode = _RGBA_MODES[channels]
        if _spills(self._width, self._height):
            self._buffer: np.ndarray | None = None
            self._store = TiledPixelStore.allocate(self._width, self._height)
        else:
            shape = (self._height, self._width)
            if channels == 3:
                shape = (self._height, self._width, 3)
            self._buffer = np.empty(shape, dtype=np.uint8)
            self._store = None

    @property
    def spills(self) -> bool:
        """Whether this writer spills to a store (large output)."""
        return self._store is not None

    def write_tile(self, box: tuple[int, int, int, int], patch: np.ndarray) -> None:
        left, top, right, bottom = (int(v) for v in box)
        patch = np.asarray(patch)
        # Clip to the output bounds (pure geometry): the shared tile grid
        # sizes edge tiles by ceil(), so a trailing region can overshoot
        # the frame (e.g. right=8196 on an 8192-wide image) while the
        # computed patch is already edge-clipped by numpy slicing — or,
        # for PIL-fed tiles, padded. Both directions are normalized here
        # so producers never reason about edge geometry themselves.
        clip_left, clip_top = max(0, left), max(0, top)
        clip_right, clip_bottom = min(self._width, right), min(self._height, bottom)
        if clip_right <= clip_left or clip_bottom <= clip_top:
            return
        patch = patch[
            clip_top - top : clip_top - top + (clip_bottom - clip_top),
            clip_left - left : clip_left - left + (clip_right - clip_left),
        ]
        left, top, right, bottom = clip_left, clip_top, clip_right, clip_bottom
        if self._store is not None:
            pil = Image.fromarray(patch, mode=self._mode).convert("RGBA")
            self._store.write_pil((left, top, right, bottom), pil)
            return
        assert self._buffer is not None
        self._buffer[top:bottom, left:right] = patch

    def finalize(self) -> Image.Image | TiledPixelStore:
        if self._store is not None:
            store, self._store = self._store, None
            return store
        assert self._buffer is not None
        out = Image.fromarray(self._buffer, mode=self._mode).convert("RGBA")
        self._buffer = None
        return out


def open_streaming_output(
    width: int, height: int, *, channels: int
) -> StreamingDiffWriter:
    """Open a tile-streamed output writer (see :class:`StreamingDiffWriter`)."""
    return StreamingDiffWriter(width, height, channels=channels)
