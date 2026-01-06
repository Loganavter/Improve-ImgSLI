from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import QTimer
from .definitions import LAYOUT_DEFINITIONS, ALL_KNOWN_WIDGETS
import logging

logger = logging.getLogger("ImproveImgSLI")

class LayoutManager:
    def __init__(self, ui, presenter=None):
        self.ui = ui
        self.presenter = presenter

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
        self._update_group("magnifier_group_container", definition.get("magnifier_group", []))
        self._update_group("record_group_container", definition.get("record_group", []))

        # Пересчитываем минимальную ширину окна после изменения видимости виджетов
        # Используем QTimer.singleShot, чтобы дать время виджетам обновиться
        if self.presenter and hasattr(self.presenter, 'image_canvas_presenter'):
            QTimer.singleShot(0, self.presenter.image_canvas_presenter.update_minimum_window_size)

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

