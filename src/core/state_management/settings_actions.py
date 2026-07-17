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

@dataclass
class SetThemeAction(Action):
    theme: str
    def __init__(self, theme: str):
        super().__init__(type=ActionType.SET_THEME); self.theme = theme
    def get_payload(self): return {"theme": self.theme}

@dataclass
class SetUIFontModeAction(Action):
    mode: str
    def __init__(self, mode: str):
        super().__init__(type=ActionType.SET_UI_FONT_MODE); self.mode = mode
    def get_payload(self): return {"mode": self.mode}

@dataclass
class SetUIFontFamilyAction(Action):
    family: str
    def __init__(self, family: str):
        super().__init__(type=ActionType.SET_UI_FONT_FAMILY); self.family = family
    def get_payload(self): return {"family": self.family}

@dataclass
class SetDebugModeEnabledAction(Action):
    enabled: bool
    def __init__(self, enabled: bool):
        super().__init__(type=ActionType.SET_DEBUG_MODE_ENABLED); self.enabled = enabled
    def get_payload(self): return {"enabled": self.enabled}

@dataclass
class SetSystemNotificationsEnabledAction(Action):
    enabled: bool
    def __init__(self, enabled: bool):
        super().__init__(type=ActionType.SET_SYSTEM_NOTIFICATIONS_ENABLED); self.enabled = enabled
    def get_payload(self): return {"enabled": self.enabled}

@dataclass
class SetVideoRecordingFpsAction(Action):
    fps: int
    def __init__(self, fps: int):
        super().__init__(type=ActionType.SET_VIDEO_RECORDING_FPS); self.fps = fps
    def get_payload(self): return {"fps": self.fps}

@dataclass
class SetShowWorkspaceTabsAction(Action):
    enabled: bool
    def __init__(self, enabled: bool):
        super().__init__(type=ActionType.SET_SHOW_WORKSPACE_TABS); self.enabled = enabled
    def get_payload(self): return {"enabled": self.enabled}

@dataclass
class SetWindowWasMaximizedAction(Action):
    was_maximized: bool
    def __init__(self, was_maximized: bool):
        super().__init__(type=ActionType.SET_WINDOW_WAS_MAXIMIZED); self.was_maximized = was_maximized
    def get_payload(self): return {"was_maximized": self.was_maximized}

@dataclass
class SetWindowGeometryAction(Action):
    x: int
    y: int
    width: int
    height: int
    def __init__(self, x: int, y: int, width: int, height: int):
        super().__init__(type=ActionType.SET_WINDOW_GEOMETRY)
        self.x = x; self.y = y; self.width = width; self.height = height
    def get_payload(self): return {"x": self.x, "y": self.y, "width": self.width, "height": self.height}

@dataclass
class SetExportFavoriteDirAction(Action):
    path: str
    def __init__(self, path: str):
        super().__init__(type=ActionType.SET_EXPORT_FAVORITE_DIR); self.path = path
    def get_payload(self): return {"path": self.path}

@dataclass
class SetKeyboardOverridesAction(Action):
    overrides: dict[str, str]
    def __init__(self, overrides: dict[str, str]):
        super().__init__(type=ActionType.SET_KEYBOARD_OVERRIDES)
        self.overrides = dict(overrides)
    def get_payload(self): return {"overrides": dict(self.overrides)}
