from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from domain.types import Point

from .context import CanvasSceneApplyContext, CanvasSceneBuildContext
from .models import CanvasSceneGraph, CanvasSceneObject
from .stacking import CanvasStackHint, CanvasStackLayer

BuildPrimaryFn = Callable[[CanvasSceneBuildContext], tuple[CanvasSceneObject, ...]]
BuildOverlayFn = Callable[[CanvasSceneGraph, CanvasSceneBuildContext], tuple[CanvasSceneObject, ...]]
ApplyFn = Callable[[CanvasSceneGraph, CanvasSceneApplyContext], None]
HitTestFn = Callable[[CanvasSceneGraph, Point], CanvasSceneObject | None]
ResolveActiveObjectIdFn = Callable[[object], str | None]
SyncGeometryFn = Callable[[CanvasSceneGraph, object], None]

@dataclass(frozen=True, slots=True)
class CanvasFeatureZOrder:
    layer: CanvasStackLayer = CanvasStackLayer.OBJECT
    priority: int = 0
    always_on_top: bool = False
    always_on_bottom: bool = False
    active_bias: bool = False
    selectable_when_hidden: bool = False
    tags: tuple[str, ...] = ()

    def stack_hint(
        self,
        *,
        layer: CanvasStackLayer | None = None,
        priority: int | None = None,
        active_bias: bool | None = None,
    ) -> CanvasStackHint:
        return CanvasStackHint(
            layer=self.layer if layer is None else layer,
            priority=self.priority if priority is None else int(priority),
            always_on_top=self.always_on_top,
            always_on_bottom=self.always_on_bottom,
            active_bias=self.active_bias if active_bias is None else bool(active_bias),
            selectable_when_hidden=self.selectable_when_hidden,
            tags=self.tags,
        )

@dataclass(frozen=True, slots=True)
class CanvasSceneFeature:
    name: str
    build_primary: BuildPrimaryFn
    build_overlay: BuildOverlayFn
    apply: ApplyFn
    hit_test: HitTestFn | None = None
    resolve_active_object_id: ResolveActiveObjectIdFn | None = None
    sync_geometry: SyncGeometryFn | None = None
    z_order: CanvasFeatureZOrder = field(default_factory=CanvasFeatureZOrder)
    primary_order: int = 100
    overlay_order: int = 100
    apply_order: int = 100
    hit_order: int = 100
