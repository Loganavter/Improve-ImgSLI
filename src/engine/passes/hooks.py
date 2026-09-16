"""Base-image pass hook seam (plan-engine-tab-migration Phase E1, hook-seam).

Interface-first pin (ruling 2) for the merged base-images pass that E2
builds on these signatures verbatim. Interface only: no pass
implementation, no GPU logic, no loop logic lives here.

Ownership split:

- The canvas tab owns *what* is resident this call: it implements
  ``resolve_specs(ctx) -> list[ResidencySpec]`` (per-call spec list built
  from its own geometry/LOD model -- fixed image-pair letterbox set on one
  side, dynamic N-slot pan/fit/zoom set on the other) and provides the
  single-tile upload ``upload_tile(...)`` through the engine realizer base.
- The engine owns *how* residency happens: the per-key
  target/protect/budget/upload loop, the shared upload deadline and
  count budget, eviction over budget, and upload order all live in
  ``TileResidencyRealizerBase.realize_specs`` and are never overridden by
  tab code.

Spelling note: the upload half of this seam is today spelled
``TileResidencyRealizerBase._upload_tile`` with a parameter shape identical
to ``BaseImagesPassHooks.upload_tile`` below (modulo the private name).
Both current realizers (the fixed-pair rhi_renderer residency realizer and
the multi-slot scene passes residency realizer) already implement exactly
that shape, so promoting it to the public seam name in the merged pass is
a rename, not a reshape. ``resolve_specs`` exists on neither side yet: the
fixed-pair side builds its spec list inside its ``realize_tile_plan``
entry, the multi-slot side inside its per-call ``realize`` entry -- E2
lifts those builders behind this name without changing what they resolve.
"""

from __future__ import annotations

from abc import ABCMeta, abstractmethod
from typing import Any, Protocol, runtime_checkable

from engine.cache.residency import ResidencySpec, TileResidencyRealizerBase

__all__ = [
    "BaseImagesPassHookBase",
    "BaseImagesPassHooks",
]


@runtime_checkable
class BaseImagesPassHooks(Protocol):
    """Tab side of the base-images residency seam (structural, E2-verbatim).

    A tab's base-image stage satisfies this protocol by resolving this
    call's residency specs from its own geometry/LOD model and by
    uploading one cropped tile per call from the engine loop. The engine
    never interprets ``ctx`` -- it is the tab's own per-frame pass
    context, passed through opaque.
    """

    def resolve_specs(self, ctx: Any) -> list[ResidencySpec]:
        """Build this call's residency spec list from the tab's own model."""
        ...

    def upload_tile(
        self,
        tile_service: Any,
        key: object,
        index: tuple[int, int],
        tile_image: Any,
        updates: Any,
        dirty_layers: dict[int, set[int]],
        region: object,
    ) -> None:
        """Upload one cropped tile; called by the engine realize loop.

        Same parameter shape as
        ``TileResidencyRealizerBase._upload_tile`` -- the merged pass
        promotes that override to this public seam name.
        """
        ...


class BaseImagesPassHookBase(TileResidencyRealizerBase, metaclass=ABCMeta):
    """Inheritance anchor for the merged pass (interface only, E2-verbatim).

    Adds the single abstract tab hook -- ``resolve_specs`` -- to the
    engine realizer base that already owns the realize loop
    (``realize_specs``) and declares the upload hook
    (``_upload_tile``, same parameter shape as
    ``BaseImagesPassHooks.upload_tile``). The merged pass subclasses this
    and fills in both tab hooks; it adds no loop, budget, eviction, or
    ordering logic of its own.
    """

    @abstractmethod
    def resolve_specs(self, ctx: Any) -> list[ResidencySpec]:
        """Build this call's residency spec list from the tab's own model.

        The engine passes ``ctx`` through opaque and realizes the
        returned specs via the inherited ``realize_specs`` loop.
        """
        raise NotImplementedError
