"""One owner for texture-array allocation: sizing, verification, shrink.

A QRhi texture array allocates **every** layer up front (mip chain included),
so its layer count is a GPU allocation decision, not a renderer-local one:
514 px RGBA8 layers at the compare tabs' old 2032-layer cap ask for ~2.9 GB,
which an integrated GPU cannot back. The failure is silent -- ``create()``
returns True on Mesa, the texture simply has no storage, and the first render
target attached to it comes back ``GL_FRAMEBUFFER_INCOMPLETE_ATTACHMENT`` (the
``MipCascadeNotReady`` black canvas, 2026-10-28).

Tabs still decide how much *residency* they want to spend (their tile budgets
differ), but the per-array number is derived here:
``plan_array_capacity`` bounds it by a per-array byte cap and the backend's
layer limit, ``ArrayResources`` then verifies the real allocation and shrinks
until the driver actually accepts it (``shrink_capacity``).
"""

from __future__ import annotations

from engine.cache.tile_texture_service import DEFAULT_MAX_ARRAY_SIZE

#: Per-array byte cap. A single texture is one allocation: unlike the tile
#: budget it cannot be evicted partially, so it must stay small enough for an
#: integrated GPU to back it. Grown only by the demand floor below.
DEFAULT_MAX_ARRAY_BYTES = 512 * 1024 * 1024

#: Never shrink below this while looking for a creatable allocation: a tiny
#: array still draws a canvas, and the draw plan drops (never mis-draws) the
#: layers that no longer fit.
MIN_ARRAY_LAYERS = 8


def array_layer_bytes(layer_px: int) -> int:
    """Bytes of one RGBA8 layer (level 0) for a square ``layer_px`` array."""
    size = int(layer_px)
    if size <= 0:
        raise ValueError(f"layer_px must be positive, got {layer_px!r}")
    return size * size * 4


def plan_array_capacity(
    *,
    layer_px: int,
    demand_layers: int = 1,
    max_array_bytes: int = DEFAULT_MAX_ARRAY_BYTES,
    hard_max: int = DEFAULT_MAX_ARRAY_SIZE,
) -> int:
    """Layers one array texture should be created with.

    ``demand_layers`` is a correctness floor, not a wish: the array SRB binds
    ``tile_arrays[0]`` only, so a canvas whose visible set needs more layers
    than the byte cap allows still has to open that many -- dropping them is a
    worse outcome than a large allocation. The byte cap therefore only lowers
    the number for canvases that do not need it, and ``ArrayResources`` shrinks
    further if the driver refuses what the floor asked for.
    """
    per_layer = array_layer_bytes(layer_px)
    by_bytes = max(1, int(max_array_bytes) // per_layer)
    wanted = max(int(demand_layers), by_bytes)
    return max(1, min(int(hard_max), wanted))


def shrink_capacity(capacity: int) -> int:
    """Next smaller allocation to try after the driver refused ``capacity``.

    Halves, never below :data:`MIN_ARRAY_LAYERS`; returns ``capacity`` itself
    once the floor is reached so the caller can stop (and raise) instead of
    looping forever.
    """
    current = max(1, int(capacity))
    if current <= MIN_ARRAY_LAYERS:
        return current
    return max(MIN_ARRAY_LAYERS, current // 2)


#: Per-process memory of what this driver actually accepted, keyed by
#: ``(backend name, layer_px)``. A canvas rebuild (new resources object for
#: the same GPU) must not pay the failed 2 GiB allocation again -- on the
#: 2026-10-28 integrated-Intel repro every rebuild spent ~2 s creating and
#: discarding the refused array.
_VERIFIED_CAPACITY: dict[tuple[str, int], int] = {}


def remembered_capacity(backend: str, layer_px: int, planned: int) -> int:
    """``planned``, lowered to what this backend already accepted (if known)."""
    known = _VERIFIED_CAPACITY.get((str(backend or ""), int(layer_px)))
    return int(planned) if known is None else min(int(planned), int(known))


def remember_capacity(backend: str, layer_px: int, capacity: int) -> None:
    """Record a capacity this backend actually backed, for later rebuilds."""
    _VERIFIED_CAPACITY[(str(backend or ""), int(layer_px))] = int(capacity)


def forget_verified_capacities() -> None:
    """Drop the memory (tests; a real process only ever learns one driver)."""
    _VERIFIED_CAPACITY.clear()


__all__ = [
    "DEFAULT_MAX_ARRAY_BYTES",
    "MIN_ARRAY_LAYERS",
    "array_layer_bytes",
    "forget_verified_capacities",
    "plan_array_capacity",
    "remember_capacity",
    "remembered_capacity",
    "shrink_capacity",
]
