from dataclasses import dataclass, field

from core.state_management.action_base import Action, ActionType

@dataclass
class InvalidateRenderCacheAction(Action):
    type: str = field(default=ActionType.INVALIDATE_RENDER_CACHE.value, kw_only=True)
    def get_payload(self): return {}

@dataclass
class InvalidateGeometryCacheAction(Action):
    type: str = field(default=ActionType.INVALIDATE_GEOMETRY_CACHE.value, kw_only=True)
    def get_payload(self): return {}

@dataclass
class ClearAllCachesAction(Action):
    type: str = field(default=ActionType.CLEAR_ALL_CACHES.value, kw_only=True)
    def get_payload(self): return {}

@dataclass
class ClearImageSlotDataAction(Action):
    slot: int
    type: str = field(default=ActionType.CLEAR_IMAGE_SLOT_DATA.value, kw_only=True)
    def get_payload(self): return {"slot": self.slot}
