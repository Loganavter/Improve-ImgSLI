from __future__ import annotations

import logging

from tabs.multi_compare.ui.layout_definitions import (
    ALL_KNOWN_WIDGETS,
    LAYOUT_DEFINITIONS,
)

logger = logging.getLogger("ImproveImgSLI")


class MultiCompareLayoutManager:
    def __init__(self, toolbar):
        self.toolbar = toolbar

    def apply_mode(self, mode_name: str) -> None:
        requested_mode = mode_name
        if mode_name not in LAYOUT_DEFINITIONS:
            logger.warning(
                "Unknown multi-compare UI mode '%s', falling back to 'beginner'",
                mode_name,
            )
            mode_name = "beginner"

        definition = LAYOUT_DEFINITIONS[mode_name]

        used_widgets = set()
        for group_widgets in definition.values():
            used_widgets.update(group_widgets)

        for widget_name in ALL_KNOWN_WIDGETS:
            if hasattr(self.toolbar, widget_name):
                widget = getattr(self.toolbar, widget_name)
                widget.setVisible(widget_name in used_widgets)

        self._update_group("line_group_container", definition.get("line_group", []))
        self._update_group("label_group_container", definition.get("label_group", []))
        self._update_group("action_group_container", definition.get("action_group", []))

    def _update_group(self, container_name: str, widget_names: list[str]) -> None:
        if not hasattr(self.toolbar, container_name):
            return

        container = getattr(self.toolbar, container_name)
        layout = container.layout()
        if layout is None:
            return

        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)

        for name in widget_names:
            if hasattr(self.toolbar, name):
                widget = getattr(self.toolbar, name)
                layout.addWidget(widget)
                widget.setVisible(True)
        container.setVisible(bool(widget_names))
