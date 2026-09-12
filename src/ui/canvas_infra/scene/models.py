from __future__ import annotations

from dataclasses import dataclass, field

from domain.types import Rect
from .stacking import CanvasStackHint

@dataclass(frozen=True)
class CanvasSceneObject:
    id: str
    kind: str
    visible: bool = True
    z_index: int = 0
    stack_hint: CanvasStackHint = field(default_factory=CanvasStackHint)

@dataclass(frozen=True)
class CanvasSceneGraph:
    bounds: Rect = field(default_factory=Rect)
    objects: tuple[CanvasSceneObject, ...] = ()
    active_object_id: str | None = None

    def get_object(self, object_id: str | None) -> CanvasSceneObject | None:
        if object_id is None:
            return None
        for obj in self.objects:
            if obj.id == object_id:
                return obj
        return None

    def iter_objects(self, kind: str | None = None):
        from .stacking import resolve_render_order

        for obj in resolve_render_order(self.objects, self.active_object_id):
            if kind is None or obj.kind == kind:
                yield obj

    def iter_pick_objects(self, kind: str | None = None):
        from .stacking import resolve_pick_order

        for obj in resolve_pick_order(self.objects, self.active_object_id):
            if kind is None or obj.kind == kind:
                yield obj

    def find_first(self, kind: str) -> CanvasSceneObject | None:
        for obj in self.iter_objects(kind=kind):
            return obj
        return None
