"""Find Action search index for the still-image Export dialog chrome."""

from __future__ import annotations

from ui.actions.search_index import SearchIndex, group

OUTPUT = group(
    "label.output_directory",
    "button.browse",
    "misc.set_as_favorite",
    "tooltip.use_favorite",
)

RESOLUTION = group(
    "label.resolution",
    "export.lock_aspect_ratio",
)

BACKGROUND = group(
    "export.background_color",
    "export.fill_background",
    "export.select_background_color",
)

ACTIONS = group(
    "misc.export",
    "common.ok",
    "common.cancel",
    "export.include_metadata",
)

EXPORT_DIALOG_SEARCH = SearchIndex.of(
    OUTPUT,
    RESOLUTION,
    BACKGROUND,
    ACTIONS,
)
