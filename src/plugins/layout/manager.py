import logging

from shared_toolkit.ui.widgets.composite.toast import ToastManager

from .definitions import ALL_KNOWN_WIDGETS, LAYOUT_DEFINITIONS

logger = logging.getLogger("ImproveImgSLI")

class LayoutManager:
    def __init__(self, ui, parent_window=None):
        self.ui = ui
        self.parent_window = parent_window
        self.toast_manager = None

        if parent_window is not None:
            image_label = getattr(ui, "image_label", None)
            self.toast_manager = ToastManager(parent_window, image_label)

    def apply_mode(self, mode_name: str):
        if mode_name not in LAYOUT_DEFINITIONS:
            logger.warning(f"Unknown UI mode '{mode_name}', falling back to 'beginner'")
            mode_name = "beginner"

        definition = LAYOUT_DEFINITIONS[mode_name]

        used_widgets = set()
        for group_widgets in definition.values():
            used_widgets.update(group_widgets)

        for widget_name in ALL_KNOWN_WIDGETS:
            if hasattr(self.ui, widget_name):
                widget = getattr(self.ui, widget_name)

                if widget_name not in used_widgets:
                    widget.setVisible(False)
                else:
                    widget.setVisible(True)

        self._update_group("line_group_container", definition.get("line_group", []))
        self._update_group("view_group_container", definition.get("view_group", []))
        self._update_group(
            "magnifier_group_container", definition.get("magnifier_group", [])
        )
        self._update_group("record_group_container", definition.get("record_group", []))

    def _update_group(self, container_name: str, widget_names: list):
        if not hasattr(self.ui, container_name):
            return

        container = getattr(self.ui, container_name)
        layout = container.layout()

        if not layout:
            return

        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)

        for name in widget_names:
            if hasattr(self.ui, name):
                widget = getattr(self.ui, name)
                layout.addWidget(widget)
                widget.setVisible(True)
