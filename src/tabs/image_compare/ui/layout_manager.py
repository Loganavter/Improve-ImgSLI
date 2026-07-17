from __future__ import annotations

import logging

from sli_ui_toolkit.widgets import ToastManager

from tabs.image_compare.ui.layout_definitions import (
    ALL_KNOWN_WIDGETS,
    LAYOUT_DEFINITIONS,
)

logger = logging.getLogger("ImproveImgSLI")


class ImageCompareLayoutManager:
    def __init__(self, ui, parent_window=None):
        # `ui` must be image_compare's own tab-owned widget (the one
        # `ImageComparePrimitivesFactory`/`ImageCompareLayoutBuilder` attach
        # all of `ALL_KNOWN_WIDGETS` and the four `*_group_container`s to),
        # never the host `Ui_ImageComparisonApp` — those widgets do not
        # exist there. Every name below is unconditionally constructed by
        # the time this class is used (`assemble_host_page` runs before
        # `apply_mode`'s first call), so a missing attribute means the
        # wrong object was passed in, not a legitimately-absent widget.
        # Let that surface as an immediate AttributeError instead of a
        # widget silently never being placed into its layout (see
        # docs/dev/tabs/isolation.md "No Implied Lookups").
        self.ui = ui
        self.parent_window = parent_window
        self.toast_manager = None

        if parent_window is not None:
            self.toast_manager = ToastManager(parent_window, ui.image_label)

    def apply_mode(self, mode_name: str):
        if mode_name not in LAYOUT_DEFINITIONS:
            logger.warning(
                "Unknown image-compare UI mode '%s', falling back to 'beginner'",
                mode_name,
            )
            mode_name = "beginner"

        definition = LAYOUT_DEFINITIONS[mode_name]

        used_widgets = set()
        for group_widgets in definition.values():
            used_widgets.update(group_widgets)

        for widget_name in ALL_KNOWN_WIDGETS:
            getattr(self.ui, widget_name).setVisible(widget_name in used_widgets)

        self._update_group("line_group_container", definition.get("line_group", []))
        self._update_group("view_group_container", definition.get("view_group", []))
        self._update_group(
            "magnifier_group_container",
            definition.get("magnifier_group", []),
        )
        self._update_group("record_group_container", definition.get("record_group", []))

    def _update_group(self, container_name: str, widget_names: list[str]):
        container = getattr(self.ui, container_name)
        layout = container.layout()
        if layout is None:
            return

        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)

        for name in widget_names:
            widget = getattr(self.ui, name)
            layout.addWidget(widget)
            widget.setVisible(True)
        container.setVisible(bool(widget_names))
