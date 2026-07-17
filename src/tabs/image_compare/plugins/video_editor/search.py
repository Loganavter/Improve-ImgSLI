"""Find Action search index for the Video Editor dialog chrome."""

from __future__ import annotations

from ui.actions.search_index import SearchIndex, group

# Logical clusters — tagged on widgets in dialog/sections.py at build time.
TOOLBAR = group(
    "video.toolbar",
    "button.play",
    "button.undo_ctrlz",
    "button.redo",
    "button.trim_to_selection",
)

RESOLUTION = group(
    "label.resolution",
    "video.lock_aspect_ratio",
    "magnifier.fit_mode_toggle",
    "export.select_background_color",
)

PREVIEW_QUALITY = group(
    "video.preview_quality",
    "video.preview_quality_full",
    "video.preview_quality_balanced",
    "video.preview_quality_performance",
    "video.preview_quality_draft",
)

EXPORT_TABS = group(
    "video.export_tabs",
    "video.standard",
    "video.manual_cli",
    "label.output",
    "video.export_log",
)

EXPORT_FOOTER = group(
    "video.export_actions",
    "action.export_video",
    "button.stop",
    "button.browse",
    "misc.set_as_favorite",
    "tooltip.use_favorite",
)

VIDEO_EDITOR_SEARCH = SearchIndex.of(
    TOOLBAR,
    RESOLUTION,
    PREVIEW_QUALITY,
    EXPORT_TABS,
    EXPORT_FOOTER,
)

# Member key → default chord hint (dialog-local; not main-window binder).
VIDEO_EDITOR_SHORTCUTS: dict[str, str] = {
    "button.play": "Space",
    "button.undo_ctrlz": "Ctrl+Z",
    "button.redo": "Ctrl+Y",
    "button.trim_to_selection": "Delete",
}
