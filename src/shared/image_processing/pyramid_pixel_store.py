"""Mipmap pyramid over :class:`TiledPixelStore`.

Level 0 is the (unified) base store; every further level ceil-halves the
previous one via a 2x2 box filter until ``min(w, h) <= COARSEST_MIN_DIM``.
Each level is a plain ``TiledPixelStore`` (own memmap spill file), so tile
addressing, leases and spill lifecycle behave identically at every level.

Levels are built finest-first (each from the previous), so consumers must
clamp their requested level to what is published so far — see
``best_level_for_scale``. The base store is owned by the document; the
pyramid owns only its derived levels.
"""

from __future__ import annotations

import logging
from typing import Callable

import numpy as np

from shared.image_processing.tiled_pixel_store import TiledPixelStore

logger = logging.getLogger("ImproveImgSLI")

# Coarsest level stops once both dimensions fit a preview-magnitude surface.
COARSEST_MIN_DIM = 1024

_BUILD_STRIP_ROWS = 1024


def estimate_total_levels(width: int, height: int) -> int:
    """Levels (including level 0) a full pyramid for a ``width``x``height``
    base will end up with — mirrors the halving stop condition in
    :meth:`PyramidPixelStore.is_complete`, used only for progress reporting."""
    levels = 1
    dim = min(width, height)
    while dim > COARSEST_MIN_DIM:
        dim = (dim + 1) // 2
        levels += 1
    return levels


def _halve_box_filter(arr: np.ndarray) -> np.ndarray:
    """2x2 box-filter halving of an (H, W, 4) uint8 array, edge-padding odd dims.

    Accumulates in place into one uint16 buffer instead of materializing a
    separate temporary array per ``+`` (the naive ``a+b+c+d`` form) -- on a
    20000px source strip this is the pyramid build's dominant cost, and the
    in-place form cuts it ~2.6x by halving the number of full-buffer passes."""
    if arr.shape[0] % 2:
        arr = np.concatenate([arr, arr[-1:]], axis=0)
    if arr.shape[1] % 2:
        arr = np.concatenate([arr, arr[:, -1:]], axis=1)
    out: np.ndarray = arr[0::2, 0::2].astype(np.uint16)
    out += arr[1::2, 0::2]
    out += arr[0::2, 1::2]
    out += arr[1::2, 1::2]
    out += 2
    out >>= 2
    return out.astype(np.uint8)


class PyramidPixelStore:
    def __init__(self, base: TiledPixelStore, tmp_dir: str | None = None):
        self._levels: list[TiledPixelStore] = [base]
        self._tmp_dir = tmp_dir
        self._base_generation = base.generation

    @property
    def base(self) -> TiledPixelStore:
        return self._levels[0]

    @property
    def level_count(self) -> int:
        return len(self._levels)

    @property
    def valid(self) -> bool:
        base = self._levels[0]
        return base.is_open and base.generation == self._base_generation

    def level(self, k: int) -> TiledPixelStore:
        return self._levels[k]

    def level_scale(self, k: int) -> float:
        """Source (level-0) pixels per level-``k`` pixel is ``2**k``; this is 1/2**k."""
        return 1.0 / float(1 << k)

    def best_level_for_scale(self, dest_scale: float) -> int:
        """Ideal level for ``dest_scale``, clamped to what is built so far."""
        from shared.rendering.lod import select_level

        return select_level(dest_scale, self.level_count)

    def is_complete(self) -> bool:
        w, h = self._levels[-1].size
        return min(w, h) <= COARSEST_MIN_DIM

    def build_next_level(
        self, should_abort: Callable[[], bool] | None = None
    ) -> bool:
        """Build one more level from the current coarsest.

        Returns True if a level was added, False if the pyramid is complete.
        On abort the partial level is discarded and False is returned.
        """
        if not self.valid or self.is_complete():
            return False
        import time

        t0 = time.perf_counter()
        prev = self._levels[-1]
        src_w, src_h = prev.size
        out_w, out_h = (src_w + 1) // 2, (src_h + 1) // 2
        level = TiledPixelStore.allocate(out_w, out_h, self._tmp_dir)
        try:
            y = 0
            while y < src_h:
                if should_abort is not None and should_abort():
                    level.close()
                    return False
                if not self.valid:
                    level.close()
                    return False
                chunk = min(_BUILD_STRIP_ROWS, src_h - y)
                # Odd trailing row is handled inside _halve_box_filter; keep
                # strips even-height so strip seams land on output rows.
                if chunk % 2 and y + chunk < src_h:
                    chunk -= 1
                strip = prev.read_array((0, y, src_w, y + chunk))
                out = _halve_box_filter(strip)
                level.write_array((0, y // 2, out_w, y // 2 + out.shape[0]), out)
                y += chunk
            level.flush()
        except Exception:
            level.close()
            raise
        self._levels.append(level)
        logger.info(
            "[Pyramid] level %d built: %dx%d in %.2fs (complete=%s)",
            len(self._levels) - 1,
            out_w,
            out_h,
            time.perf_counter() - t0,
            self.is_complete(),
        )
        return True

    def build_all(self, should_abort: Callable[[], bool] | None = None) -> None:
        while self.build_next_level(should_abort=should_abort):
            pass

    @classmethod
    def build_from(
        cls,
        base: TiledPixelStore,
        tmp_dir: str | None = None,
        should_abort: Callable[[], bool] | None = None,
    ) -> "PyramidPixelStore":
        pyramid = cls(base, tmp_dir)
        pyramid.build_all(should_abort=should_abort)
        return pyramid

    def close(self) -> None:
        """Close derived levels only; the base store is owned by the document."""
        for level in self._levels[1:]:
            level.close()
        del self._levels[1:]
