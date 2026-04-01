from dataclasses import dataclass

from core.state_management.action_base import Action, ActionType

@dataclass
class SetLanguageAction(Action):
    language: str
    def __init__(self, language: str):
        super().__init__(type=ActionType.SET_LANGUAGE); self.language = language
    def get_payload(self): return {"language": self.language}

@dataclass
class SetUIModeAction(Action):
    mode: str
    def __init__(self, mode: str):
        super().__init__(type=ActionType.SET_UI_MODE); self.mode = mode
    def get_payload(self): return {"mode": self.mode}

@dataclass
class SetAutoCropBlackBordersAction(Action):
    enabled: bool
    def __init__(self, enabled: bool):
        super().__init__(type=ActionType.SET_AUTO_CROP_BLACK_BORDERS); self.enabled = enabled
    def get_payload(self): return {"enabled": self.enabled}
