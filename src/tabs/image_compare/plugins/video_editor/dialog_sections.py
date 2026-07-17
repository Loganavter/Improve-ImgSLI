"""Shim: section builders live in ``dialog.sections``."""

from __future__ import annotations

from tabs.image_compare.plugins.video_editor.dialog.sections import (
    build_settings_panel,
    create_export_tabs,
    create_fps_settings,
    create_log_tab,
    create_manual_export_tab,
    create_output_tab,
    create_preview_quality_settings,
    create_quality_stack,
    create_resolution_settings,
    create_standard_export_tab,
    create_timeline_scroll_area,
    create_toolbar,
)

__all__ = [
    "build_settings_panel",
    "create_export_tabs",
    "create_fps_settings",
    "create_log_tab",
    "create_manual_export_tab",
    "create_output_tab",
    "create_preview_quality_settings",
    "create_quality_stack",
    "create_resolution_settings",
    "create_standard_export_tab",
    "create_timeline_scroll_area",
    "create_toolbar",
]
