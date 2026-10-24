"""One pure engine value describing a canvas tab's tile policy.

Before this module each canvas surface carried the same residency knobs as
scattered module constants and inline booleans (image compare, multi compare,
the engine's own ``TiledImageView``), so the differences between them were only
discoverable by reading three renderers side by side. ``TilePolicy`` names the
knobs once; each surface builds its own frozen instance from the numbers it
already used (``tests/contracts/test_tile_policy_matrix.py`` pins the measured
matrix, ``tests/contracts/test_tile_policy_extraction.py`` pins that the
fallback entry reproduces ``resolve_fallback_lod``'s ``atomic`` truth table).

Deliberately NOT here: geometry, crop/letterbox/magnifier/diff spec building,
residency realisation and the texture-array derivation all stay tab-side. This
is a value, not a service -- no Qt/QRhi import, no I/O, no module state, so the
contract tier can read it without a Qt import.
"""

from __future__ import annotations

from dataclasses import dataclass

_LOD_MODES = ("immediate", "settle")


@dataclass(frozen=True)
class TilePolicy:
    """The tile-policy knobs one canvas surface uses.

    ``lod_mode``/``settle_ms`` mirror ``engine.gpu.tiled_image_view.LodPolicy``
    (``"settle"`` holds the currently drawn pyramid level until the target is
    resident, ``settle_ms`` is its debounce; ``None`` = no settle window).

    ``atomic_on_*`` select which transitions the fallback entry holds whole
    (``resolve_frame_fallback``): the old tier is drawn alone until the new one
    promotes instead of layering a partially uploaded grid over it.

    ``first_paint_hold`` and ``pin_coarsest`` record wire-up decisions that
    live outside the fallback entry (the first-paint placeholder hold, and
    ``TileTextureService.pin_coarsest_level`` for the fallback baseline).

    ``tile_budget_bytes``/``host_cache_budget_bytes`` are the GPU resident-tile
    and host QImage cache budgets; ``array_capacity`` is the pre-sized
    texture-array layer count. Each surface passes the value its own derivation
    already produced -- the derivation itself stays in the tab module.
    """

    lod_mode: str
    settle_ms: float | None
    atomic_on_content_swap: bool
    atomic_on_hires_flip: bool
    atomic_on_level_change: bool
    first_paint_hold: bool
    pin_coarsest: bool
    tile_budget_bytes: int
    host_cache_budget_bytes: int
    array_capacity: int

    def __post_init__(self) -> None:
        if self.lod_mode not in _LOD_MODES:
            raise ValueError(
                f"TilePolicy.lod_mode must be one of {_LOD_MODES}, "
                f"got {self.lod_mode!r}"
            )
        if self.settle_ms is not None and float(self.settle_ms) < 0.0:
            raise ValueError("TilePolicy.settle_ms must be None or >= 0")
        for name in (
            "tile_budget_bytes",
            "host_cache_budget_bytes",
            "array_capacity",
        ):
            if int(getattr(self, name)) < 0:
                raise ValueError(f"TilePolicy.{name} must be >= 0")

    @property
    def uses_settle(self) -> bool:
        """True when this surface debounces LOD commits instead of committing
        every frame (``lod_mode == "settle"``)."""
        return self.lod_mode == "settle"

    def atomic_for(
        self,
        *,
        is_content_swap: bool = False,
        is_hires_flip: bool = False,
        is_level_hold: bool = False,
    ) -> bool:
        """The fallback entry's ``atomic`` decision for one frame.

        A transition is atomic only where THIS policy opts in -- the caller
        still owns the per-frame detection of what kind of transition it is
        (content swap, hires flip, LOD level hold), so a surface with the flag
        off keeps the progressive reveal it had before the extraction.
        """
        return bool(
            (self.atomic_on_content_swap and is_content_swap)
            or (self.atomic_on_hires_flip and is_hires_flip)
            or (self.atomic_on_level_change and is_level_hold)
        )
