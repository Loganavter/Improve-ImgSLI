"""Quick-look canvas: additive tiled single-source path.

Split from ``preview_canvas.py`` (plan-gallery-split-2026-10-17, Part C2).
Bodies moved verbatim; names and signatures unchanged. Plain functions
take the canvas widget as their first argument (``CODE_PATTERNS.md`` --
thin owner + module functions).
"""

from __future__ import annotations

import logging
import os

from engine.gpu.tiled_image_view import (
    SingleImageTiledView,
    TiledImageSource,
    load_tiled_image_shader,
)

logger = logging.getLogger("ImproveImgSLI")


# -- tiled single-source path (additive) --------------------------------------


def set_tiled_source(self, key, store) -> None:
    """Register a full ``TiledPixelStore`` to draw from array tiles.

    Additive: the raster/cover path keeps serving until this tiled
    source is *fully covered* (every visible tile resident); a missing
    slot fails closed per tile, so a half-uploaded grid never
    substitutes a neighbor and never surfaces as a transparent frame.
    Never raises.
    """
    try:
        self._tiled_source = (key, store)
        self._tile_bound_source = None
        self._tile_level_ready = False
    except Exception:
        self._tiled_source = None
        return
    try:
        self._reset_tiled_pump_state()
    except Exception:
        pass
    try:
        self._ensure_tile_renderer()
    except Exception:
        logger.debug("QuickLook preview: tile renderer setup failed open", exc_info=True)
    try:
        self.update()
    except Exception:
        pass


def clear_tiled_source(self) -> None:
    """Drop the tiled source + its GPU tiles (walk/close). Never raises."""
    try:
        self._tiled_source = None
        self._tile_bound_source = None
        self._tile_level_ready = False
    except Exception:
        pass
    try:
        self._reset_tiled_pump_state()
    except Exception:
        pass
    try:
        renderer = self._tile_renderer
        if renderer is not None:
            renderer.clear_source()
    except Exception:
        pass
    try:
        self.update()
    except Exception:
        pass


def _sampler_for_tiles(self, name):
    """Lazy ``linear`` sampler for the tile-array SRB (owned here)."""
    try:
        if name != "linear":
            return None
        existing = self._tile_sampler
        if existing is not None:
            return existing
        rhi = self.rhi()
        if rhi is None:
            return None
        from PySide6.QtGui import QRhiSampler

        _mip = (
            QRhiSampler.Filter.None_
            if os.environ.get("IMGSLI_QL_NO_MIPS")
            else QRhiSampler.Filter.Linear
        )
        sampler = rhi.newSampler(
            QRhiSampler.Filter.Linear,
            QRhiSampler.Filter.Linear,
            _mip,
            QRhiSampler.AddressMode.ClampToEdge,
            QRhiSampler.AddressMode.ClampToEdge,
        )
        sampler.setName(b"ql-linear-sampler")
        if not sampler.create():
            return None
        self._tile_sampler = sampler
        return sampler
    except Exception:
        return None


def _ensure_tile_renderer(self):
    """Construct (once) + bind the engine tiled view to the held source.

    The renderer is ``engine.gpu.tiled_image_view.SingleImageTiledView``;
    QL supplies only its RHI/sampler callables, the engine shader loader
    and the ``ql`` name prefix. The source is a ``TiledImageSource`` with
    the demand pyramid's built levels (coarsest-first, finest/level-0
    last) so the VIEW owns LOD selection + the no-seam hold; QL does not
    hand-bind a level. ``set_source`` is (re)bound only when the
    ``(key, store, levels)`` identity changes -- rebinding every frame
    would drop and re-register the whole tile grid (a permanent
    clear/re-upload loop). ``_tile_level_ready`` marks a genuine
    multi-level binding (>= 2 registered levels): only then is the view's
    ``covered`` seam-safe (a single-level full-res draw shown downscaled
    seams at mip edges).

    The view's LOD selection uses the same ``select_level`` math the
    demand build uses, so the drawn level and the requested level can
    never disagree.
    """
    try:
        if self.rhi() is None:
            return None
        renderer = self._tile_renderer
        if renderer is None:
            renderer = SingleImageTiledView(
                rhi_getter=lambda: self.rhi(),
                sampler_getter=self._sampler_for_tiles,
                load_shader=load_tiled_image_shader,
                name_prefix="ql",
            )
            self._tile_renderer = renderer
        source = self._tiled_source
        if source is not None:
            key, store = source
            if store is not None:
                levels = self._ql_bound_levels(key)
                ident = (
                    key,
                    id(store),
                    tuple((level_key, id(level_store)) for level_key, level_store in levels),
                )
                bound = getattr(self, "_tile_bound_source", None)
                if bound != ident:
                    renderer.set_source(
                        TiledImageSource(
                            key=key,
                            store=store,
                            levels=levels or None,
                        )
                    )
                    self._tile_bound_source = ident
                    self._tile_level_ready = len(levels) > 1
                    try:
                        from tabs.image_gallery.debug import ql_cover

                        _pyr = getattr(self, "_ql_pyramid", None)
                        ql_cover(
                            "tiled bind: store=%s levels=%s pyr=%s "
                            "pyr_levels=%s",
                            getattr(store, "size", None),
                            len(levels),
                            bool(_pyr is not None),
                            int(getattr(_pyr, "level_count", 0) or 0)
                            if _pyr is not None
                            else 0,
                        )
                    except Exception:
                        pass
        return renderer
    except Exception:
        logger.debug("QuickLook preview: tile renderer ensure failed open", exc_info=True)
        return None


def _ql_bound_levels(self, key) -> tuple:
    """The built pyramid levels for ``key``, or ``()`` when none.

    Thin read over the shared demand service's ``levels_sequence`` (built
    levels coarsest-first, level 0 last) so QL never hand-picks a level.
    Read-only: the service is created on the GUI thread (``_maybe_demand_build``);
    this may run on the render thread, so it must NOT create a coordinator.
    A missing service means no pyramid is bound -> ``()``. Never raises.
    """
    try:
        svc = getattr(self, "_ql_demand_svc", None)
        pyr = getattr(self, "_ql_pyramid", None)
        if svc is None or pyr is None:
            return ()
        if not bool(getattr(pyr, "valid", False)):
            return ()
        return tuple(svc.levels_sequence(pyr, key=key))
    except Exception:
        return ()


def _destroy_tile_renderer(self) -> None:
    """Release the tile renderer + sampler (never raises)."""
    try:
        renderer = self._tile_renderer
        self._tile_renderer = None
        self._tile_bound_source = None
        self._tile_level_ready = False
        if renderer is not None:
            renderer.release()
    except Exception:
        pass
    try:
        self._reset_tiled_pump_state()
    except Exception:
        pass
    try:
        sampler = self._tile_sampler
        self._tile_sampler = None
        if sampler is not None:
            sampler.destroy()
    except Exception:
        pass
