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
import operator
from typing import TYPE_CHECKING, Callable

import numpy as np

from engine.store.tiled_pixel_store import TiledPixelStore

if TYPE_CHECKING:
    from PySide6.QtGui import QImage

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

    @property
    def generation(self) -> int:
        """Base-store generation this pyramid was built against.

        Stable snapshot taken at construction: a reunified base bumps its
        own generation, so comparing this token against the live base
        generation tells consumers whether sampled levels are stale.
        """
        return self._base_generation

    def level(self, k: int) -> TiledPixelStore:
        return self._levels[k]

    def is_level_built(self, k: int) -> bool:
        """Whether level ``k`` exists and is readable right now."""
        if isinstance(k, bool) or not isinstance(k, int):
            return False
        if k < 0 or k >= len(self._levels):
            return False
        if not self.valid:
            return False
        try:
            return bool(self._levels[k].is_open)
        except Exception:
            return False

    def level_if_built(self, k: int) -> TiledPixelStore | None:
        """Level ``k``'s store, or None when it is not built.

        Sampler idiom: never raises IndexError — out-of-range, wrongly
        typed, stale-pyramid and closed-level lookups all fail closed to
        None so callers show a gap instead of a neighbor's bytes.
        """
        if not self.is_level_built(k):
            return None
        return self._levels[k]

    def best_level_for_scale(self, dest_scale: float) -> int:
        """Ideal level for ``dest_scale``, clamped to what is built so far."""
        from engine.cache.lod import select_level

        return select_level(dest_scale, self.level_count)

    def best_pixels(
        self, rect: tuple[int, int, int, int], dest_scale: float
    ) -> QImage | None:
        """Sample ``rect`` from the best built level as a QImage, or None.

        ``rect`` is in level-0 source px (``read_array`` box convention:
        ``(left, top, right, bottom)``); ``dest_scale`` is display-px per
        level-0 px and only selects the level via
        :meth:`best_level_for_scale`. The returned image holds the level's
        native pixels for the mapped box — no resampling, so content stays
        bit-identical with what the level store holds.

        Fails closed: invalid/empty/out-of-bounds rects, an unparsable
        scale, a stale pyramid, or an unreadable selected level all yield
        None (gap) — never a neighboring level's bytes. Reads through
        ``read_array`` only; never materializes a full frame.
        """
        from PySide6.QtGui import QImage

        try:
            left, top, right, bottom = (operator.index(v) for v in rect)
        except Exception:
            return None
        if right <= left or bottom <= top:
            return None
        try:
            scale = float(dest_scale)
        except Exception:
            return None
        if not self.valid:
            return None
        try:
            base_w, base_h = self._levels[0].size
        except Exception:
            return None
        left = max(0, left)
        top = max(0, top)
        right = min(base_w, right)
        bottom = min(base_h, bottom)
        if right <= left or bottom <= top:
            return None
        try:
            k = self.best_level_for_scale(scale)
        except Exception:
            return None
        level = self.level_if_built(k)
        if level is None:
            return None
        try:
            level_w, level_h = level.size
        except Exception:
            return None
        step = 1 << k
        level_box = (
            left // step,
            top // step,
            min((right + step - 1) // step, level_w),
            min((bottom + step - 1) // step, level_h),
        )
        ll, lt, lr, lb = level_box
        if lr <= ll or lb <= lt:
            return None
        try:
            arr = np.ascontiguousarray(level.read_array(level_box))
        except Exception:
            return None
        if arr.shape[0] != lb - lt or arr.shape[1] != lr - ll:
            return None
        width, height = lr - ll, lb - lt
        return QImage(
            arr.data,
            width,
            height,
            width * 4,
            QImage.Format.Format_RGBA8888,
        ).copy()

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

    @classmethod
    def coarse_from_source(
        cls, path: str, *, long_edge: int = 1024, tmp_dir: str | None = None
    ) -> TiledPixelStore | None:
        """Build a bounded coarse store straight from a source file.

        Phase-1 fast path: a small full-image stand-in (long edge capped at
        ``long_edge``) decoded without ever materializing the full frame —
        shrink-on-load via libvips ``thumbnail`` when the format streams,
        else a bounded reader scaled-read. Fails closed to None when the
        source cannot be read this way; callers then fall back to the
        regular base decode plus pyramid build. Spills through
        ``TiledPixelStore`` strip writes only.
        """
        from PIL import Image

        try:
            cap = max(1, operator.index(long_edge))
        except Exception:
            return None
        try:
            from shared.image_processing.progressive_loader import (
                pyvips_can_stream,
            )

            streamable = pyvips_can_stream(path)
        except Exception:
            streamable = False
        if streamable:
            try:
                return cls._coarse_from_source_vips(path, cap, tmp_dir)
            except Exception:
                logger.debug("[Pyramid] vips coarse decode failed for %s", path)
                return None
        try:
            with Image.open(path) as probe:
                src_w, src_h = probe.size
            from shared.image_processing.progressive_loader import (
                _ensure_supported_dimensions,
            )

            _ensure_supported_dimensions(src_w, src_h, str(path))
            with Image.open(path) as img:
                try:
                    img.draft(img.mode, (cap * 2, cap * 2))
                except Exception:
                    pass
                thumb = img.copy()
                thumb.thumbnail((cap, cap), Image.Resampling.BILINEAR)
                rgba = thumb.convert("RGBA")
                return TiledPixelStore.from_pil(rgba, tmp_dir)
        except Exception:
            logger.debug("[Pyramid] reader coarse decode failed for %s", path)
            return None

    @staticmethod
    def _coarse_from_source_vips(
        path: str, cap: int, tmp_dir: str | None
    ) -> TiledPixelStore:
        """Shrink-on-load coarse decode; raises on any failure."""
        import pyvips

        # Parity decision (pyramid wave-B1): pyvips ``thumbnail`` honors EXIF
        # orientation tags by default (auto-rotate), but the PIL branch below
        # (``Image.thumbnail``) and the legacy gallery ladder never transpose
        # — no ``exif_transpose`` anywhere in the thumb path. Passing
        # ``no_rotate`` keeps BOTH coarse branches unrotated and identical in
        # orientation. Honoring orientation everywhere is a deliberate
        # behavior change and stays a follow-up, not part of this epic.
        thumb = pyvips.Image.thumbnail(
            str(path),
            cap,
            height=cap,
            size=pyvips.enums.Size.DOWN,
            no_rotate=True,
        )
        if not thumb.hasalpha():
            thumb = thumb.bandjoin(255)
        if thumb.format != "uchar":
            thumb = thumb.cast("uchar")
        out_w, out_h = int(thumb.width), int(thumb.height)
        buf = thumb.write_to_memory()
        plane = np.ndarray(
            buffer=buf, dtype=np.uint8, shape=(out_h, out_w, thumb.bands)
        )
        if plane.shape[2] != 4:
            fixed = np.empty((out_h, out_w, 4), dtype=np.uint8)
            fixed[:, :, :3] = plane[:, :, :3]
            fixed[:, :, 3] = 255
            plane = fixed
        store = TiledPixelStore.allocate(out_w, out_h, tmp_dir)
        try:
            y = 0
            while y < out_h:
                chunk = min(_BUILD_STRIP_ROWS, out_h - y)
                store.write_array(
                    (0, y, out_w, y + chunk),
                    np.ascontiguousarray(plane[y : y + chunk]),
                )
                y += chunk
            store.flush()
        except Exception:
            store.close()
            raise
        return store

    def close(self) -> None:
        """Close derived levels only; the base store is owned by the document."""
        for level in self._levels[1:]:
            level.close()
        del self._levels[1:]


def ensure_level(pyramid, k, should_abort=None) -> bool:
    """Build demand levels until level ``k`` lands (GIMP-style pull).

    Loops ``build_next_level`` until ``is_level_built(k)`` holds or the
    build stops (complete / abort / invalid base). Never builds past
    ``k`` — the loop exits the moment ``k`` is readable.

    Fail-open: invalid ``k`` (bool, non-int, negative), a missing/dead
    pyramid, an abort, or any build error all yield False — never raises.
    """
    try:
        if pyramid is None or not hasattr(pyramid, "is_level_built"):
            return False
        if isinstance(k, bool) or not isinstance(k, int) or k < 0:
            return False
        if k == 0:
            return bool(pyramid.is_level_built(0))
        try:
            if bool(pyramid.is_level_built(k)):
                return True
        except Exception:
            return False
        try:
            build_next = pyramid.build_next_level
        except Exception:
            return False
        while True:
            try:
                if bool(pyramid.is_level_built(k)):
                    return True
            except Exception:
                return False
            try:
                progressed = build_next(should_abort=should_abort)
            except Exception:
                return False
            if not progressed:
                try:
                    return bool(pyramid.is_level_built(k))
                except Exception:
                    return False
    except Exception:
        return False


def invalidate_levels(pyramid, from_k=None) -> int:
    """Drop superseded derived levels ``k >= from_k``; never raises.

    ``from_k=None`` drops every derived level (all but the level-0
    base). ``from_k<=1`` likewise drops all derived levels; level 0 is
    never dropped. Returns the count dropped. Generations are untouched
    — ``valid``/``generation`` guards keep working, and dropped levels
    read as unbuilt via the existing ``is_level_built`` (out-of-range).
    Invalid input (no pyramid, bool/non-int ``from_k``) is a fail-open
    no-op returning 0.
    """
    try:
        if pyramid is None or not hasattr(pyramid, "is_level_built"):
            return 0
        levels = getattr(pyramid, "_levels", None)
        if not isinstance(levels, list) or len(levels) <= 1:
            return 0
        if from_k is None:
            start = 1
        elif isinstance(from_k, bool) or not isinstance(from_k, int):
            return 0
        else:
            start = max(1, from_k)
        if start >= len(levels):
            return 0
        dropped = levels[start:]
        del levels[start:]
        count = 0
        for level in dropped:
            try:
                level.close()
            except Exception:
                pass
            count += 1
        return count
    except Exception:
        return 0
