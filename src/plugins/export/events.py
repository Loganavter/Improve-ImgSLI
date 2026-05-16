from __future__ import annotations

from dataclasses import dataclass

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
