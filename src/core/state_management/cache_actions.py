from dataclasses import dataclass

from core.state_management.action_base import Action, ActionType

@dataclass
class InvalidateRenderCacheAction(Action):
    def __init__(self):
        super().__init__(type=ActionType.INVALIDATE_RENDER_CACHE)
    def get_payload(self): return {}

@dataclass
class InvalidateGeometryCacheAction(Action):
    def __init__(self):
        super().__init__(type=ActionType.INVALIDATE_GEOMETRY_CACHE)
    def get_payload(self): return {}

@dataclass
class ClearAllCachesAction(Action):
    def __init__(self):
        super().__init__(type=ActionType.CLEAR_ALL_CACHES)
    def get_payload(self): return {}

@dataclass
class ClearImageSlotDataAction(Action):
    slot: int
    def __init__(self, slot: int):
        super().__init__(type=ActionType.CLEAR_IMAGE_SLOT_DATA); self.slot = slot
    def get_payload(self): return {"slot": self.slot}
