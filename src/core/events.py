

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, TypeVar, runtime_checkable
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QColor

@runtime_checkable
class Event(Protocol):
    pass

T = TypeVar('T', bound=Event)

@dataclass(frozen=True)
class CoreUpdateRequestedEvent:
    pass

@dataclass(frozen=True)
class CoreErrorOccurredEvent:
    error: str
    details: str | None = None

@dataclass(frozen=True)
class ViewportSetSplitPositionEvent:
    position: float

@dataclass(frozen=True)
class ViewportUpdateMagnifierSizeRelativeEvent:
    relative_size: float

@dataclass(frozen=True)
class ViewportUpdateCaptureSizeRelativeEvent:
    relative_size: float

@dataclass(frozen=True)
class ViewportUpdateMovementSpeedEvent:
    speed: float

@dataclass(frozen=True)
class ViewportSetMagnifierPositionEvent:
    position: QPointF

@dataclass(frozen=True)
class ViewportSetMagnifierInternalSplitEvent:
    split_position: float

@dataclass(frozen=True)
class ViewportToggleMagnifierPartEvent:
    part: str
    visible: bool

@dataclass(frozen=True)
class ViewportUpdateMagnifierCombinedStateEvent:
    pass

@dataclass(frozen=True)
class ViewportToggleOrientationEvent:
    is_horizontal: bool

@dataclass(frozen=True)
class ViewportToggleMagnifierOrientationEvent:
    is_horizontal: bool

@dataclass(frozen=True)
class ViewportToggleFreezeMagnifierEvent:
    freeze: bool

@dataclass(frozen=True)
class ViewportOnSliderPressedEvent:
    slider_name: str

@dataclass(frozen=True)
class ViewportOnSliderReleasedEvent:
    slider_name: str
    provider: str | None = None

@dataclass(frozen=True)
class ViewportSetMagnifierVisibilityEvent:
    left: bool
    center: bool
    right: bool

@dataclass(frozen=True)
class ViewportToggleMagnifierEvent:
    enabled: bool

@dataclass(frozen=True)
class ExportToggleRecordingEvent:
    pass

@dataclass(frozen=True)
class ExportTogglePauseRecordingEvent:
    pass

@dataclass(frozen=True)
class ExportExportRecordedVideoEvent:
    pass

@dataclass(frozen=True)
class ExportOpenVideoEditorEvent:
    pass

@dataclass(frozen=True)
class ExportPasteImageFromClipboardEvent:
    pass

@dataclass(frozen=True)
class ExportQuickSaveComparisonEvent:
    pass

@dataclass(frozen=True)
class AnalysisSetChannelViewModeEvent:
    mode: str

@dataclass(frozen=True)
class AnalysisToggleDiffModeEvent:
    pass

@dataclass(frozen=True)
class AnalysisSetDiffModeEvent:
    mode: str

@dataclass(frozen=True)
class AnalysisMetricsUpdatedEvent:
    payload: dict

@dataclass(frozen=True)
class AnalysisRequestMetricsEvent:
    payload: dict | None = None

@dataclass(frozen=True)
class SettingsChangeLanguageEvent:
    lang_code: str

@dataclass(frozen=True)
class SettingsToggleIncludeFilenamesInSavedEvent:
    include: bool

@dataclass(frozen=True)
class SettingsApplyFontSettingsEvent:
    size: int
    weight: int
    color: QColor
    bg_color: QColor
    draw_bg: bool
    placement: str
    alpha: int

@dataclass(frozen=True)
class SettingsToggleDividerLineVisibilityEvent:
    visible: bool

@dataclass(frozen=True)
class SettingsSetDividerLineColorEvent:
    color: QColor

@dataclass(frozen=True)
class SettingsToggleMagnifierDividerVisibilityEvent:
    visible: bool

@dataclass(frozen=True)
class SettingsSetMagnifierDividerColorEvent:
    color: QColor

@dataclass(frozen=True)
class SettingsToggleAutoCropBlackBordersEvent:
    enabled: bool

@dataclass(frozen=True)
class SettingsSetDividerLineThicknessEvent:
    thickness: int

@dataclass(frozen=True)
class SettingsSetMagnifierDividerThicknessEvent:
    thickness: int

@dataclass(frozen=True)
class SettingsUIModeChangedEvent:
    ui_mode: str

@dataclass(frozen=True)
class ComparisonUIUpdateEvent:
    components: tuple = ()

@dataclass(frozen=True)
class ComparisonErrorEvent:
    error: str

@dataclass(frozen=True)
class ComparisonUpdateRequestedEvent:
    pass

@dataclass(frozen=True)
class MagnifierAddedEvent:
    magnifier_id: str

@dataclass(frozen=True)
class MagnifierRemovedEvent:
    magnifier_id: str

@dataclass(frozen=True)
class PluginEvent:
    plugin_name: str
    stage: str

