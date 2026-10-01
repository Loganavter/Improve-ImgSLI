"""Shared pyramid demand policy: which level a view needs and how to request it.

Engine-owned glue over :mod:`engine.cache.lod` (the level math) and the
pyramid-build coordinator (the async build). Tabs declare a source plus a
:class:`DemandPolicy` and consume a level; no tab re-implements the
``select_level``/``dest_scale_fit`` math or the coordinator call shape.

The service carries the :class:`DemandPolicy`, the single shared full-res
decode entry, and answers:

* what level a view at a given zoom/framebuffer wants (:meth:`level_for_view`),
* how to request that level (:meth:`ensure_level`),
* the built level's store, if any (:meth:`level_store`),
* the built levels in the order :class:`~engine.gpu.tiled_image_view.TiledImageSource`
  expects -- coarsest first, finest (level 0) last (:meth:`levels_sequence`),
* the full-resolution decode with an effective edge cap (:meth:`decode_full`).

The decode itself (:func:`decode_full_store`) is the single implementation
tabs delegate to; it never raises and applies an optional post-decode edge
cap (``None`` = uncapped).
"""

from __future__ import annotations

from dataclasses import dataclass

from engine.cache.lod import LevelKey, demand_level, dest_scale_fit


def _close_quiet(store) -> None:
    """Close ``store`` swallowing every failure (never raises)."""
    try:
        store.close()
    except Exception:
        pass


def decode_full_store(path, *, cap_edge: int | None = None, tmp_dir=None):
    """Single shared full-res decode: ``TiledPixelStore.from_path`` + optional
    post-decode edge cap (``None`` = uncapped). Never raises; ``None`` on
    failure or when ``max(w, h) > cap_edge``. Closes the store on cap/read
    failure.

    Pure Python + PIL/pyvips + memmap -- no Qt. The spill dir is resolved on
    the GUI thread and passed in as ``tmp_dir``; a huge source fails open to
    ``None`` so callers keep their bounded/coarse surface.
    """
    try:
        from engine.store.tiled_pixel_store import TiledPixelStore

        try:
            store = TiledPixelStore.from_path(str(path), tmp_dir)
        except Exception:
            return None
        try:
            w, h = store.size
            w, h = int(w), int(h)
        except Exception:
            _close_quiet(store)
            return None
        if w <= 0 or h <= 0:
            _close_quiet(store)
            return None
        if cap_edge is not None:
            try:
                cap = int(cap_edge)
            except Exception:
                cap = None
            if cap is not None and max(w, h) > cap:
                _close_quiet(store)
                return None
        return store
    except Exception:
        return None


@dataclass(frozen=True)
class DemandPolicy:
    """How a tab wants pyramid levels demanded.

    ``cap_edge`` is the decode cap (``None`` = uncapped) consumed by
    :meth:`PyramidDemandService.decode_full`, and ``settle`` gates promotion
    on a quiescent cascade (surfaced to the view as its ``LodPolicy``).
    """

    cap_edge: int | None = None
    mode: str = "demand"
    settle: bool = False

    def __post_init__(self) -> None:
        if self.mode not in ("demand", "eager"):
            raise ValueError(
                f"DemandPolicy.mode must be 'demand' or 'eager', got {self.mode!r}"
            )


class PyramidDemandService:
    """Shared pyramid demand policy: which level a view needs and how to
    request it. Engine-owned; no tab imports."""

    def __init__(
        self,
        *,
        coordinator,
        decode=None,
        policy: DemandPolicy | None = None,
    ) -> None:
        self._coordinator = coordinator
        self._decode = decode if decode is not None else decode_full_store
        self._policy = policy if policy is not None else DemandPolicy()

    @property
    def policy(self) -> DemandPolicy:
        return self._policy

    def decode_full(self, path, *, cap_edge: int | None = None, tmp_dir=None):
        """Decode ``path`` at the effective edge cap; never raises (``None``).

        Effective cap = explicit ``cap_edge`` when not ``None``, else
        ``self.policy.cap_edge`` (which may itself be ``None`` = uncapped).
        Delegates to the injected ``decode`` (module :func:`decode_full_store`
        by default), called as ``decode(path, cap_edge=..., tmp_dir=...)``.
        """
        try:
            effective = self._policy.cap_edge if cap_edge is None else cap_edge
            return self._decode(path, cap_edge=effective, tmp_dir=tmp_dir)
        except Exception:
            return None

    def level_for_view(
        self,
        store,
        *,
        fb_size,
        zoom,
        level_count: int | None = None,
    ) -> int:
        """Level a fit-to-box view at ``zoom`` wants; never raises (0 on error)."""
        try:
            try:
                w = int(store.size[0])
                h = int(store.size[1])
            except Exception:
                w = h = 0
            if w <= 0 or h <= 0:
                return 0
            dest_scale = dest_scale_fit(tuple(fb_size), (w, h), zoom)
            n = 0
            if level_count is not None:
                try:
                    n = int(level_count)
                except Exception:
                    n = 0
            if n <= 0:
                try:
                    n = int(store.level_count)
                except Exception:
                    n = 1
            if n <= 0:
                n = 1
            return int(demand_level(dest_scale, n))
        except Exception:
            return 0

    def ensure_level(
        self,
        store,
        level: int,
        *,
        should_abort=None,
        on_ready=None,
    ) -> None:
        """Request ``level`` from the coordinator unless it is base/already built.

        Level 0 is always resident and a built level is a no-op; otherwise the
        coordinator's ``demand_level`` is called. Never raises."""
        try:
            k = int(level)
            if k <= 0:
                return
            if store.is_level_built(k):
                return
            self._coordinator.demand_level(
                store,
                k,
                should_abort=should_abort,
                on_ready=on_ready,
            )
        except Exception:
            pass

    def level_store(self, store, level: int):
        """Built level's store, or ``None`` (fail-closed, never raises)."""
        try:
            return store.level_if_built(level)
        except Exception:
            return None

    def levels_sequence(self, store, *, key):
        """Built levels as ``(level_key, store)`` pairs, coarsest first.

        Pyramids build upward from level 0, so built levels are exactly
        ``0..m`` for the highest built ``m``. The returned tuple is ordered
        ``m, m-1, ..., 0`` (finest last) to match ``TiledImageSource.levels``
        position-to-level numbering. Level 0 uses a ``None`` key (the source
        key); coarser levels use ``LevelKey(key, level, store.generation)``.
        No built level (or a dead store) yields ``()``. Never raises."""
        try:
            level_count = int(store.level_count)
            built = [
                level
                for level in range(level_count)
                if store.is_level_built(level)
            ]
            if not built:
                return ()
            m = max(built)
            generation = store.generation
            out = []
            for level in range(m, -1, -1):
                if level == 0:
                    level_key = None
                else:
                    level_key = LevelKey(key, level, generation)
                out.append((level_key, store.level_if_built(level)))
            return tuple(out)
        except Exception:
            return ()
