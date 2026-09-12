from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication, QIcon
from shared_toolkit.ui.themed_dialog import ThemedDialog
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.widgets import Button, Label, OverlayScrollArea

from plugins.image_properties.layout_geometry import apply_image_properties_dialog_geometry
from resources.translations import get_current_language
from resources.translations import tr as app_tr
from shared_toolkit.ui.layout_sizing import handle_application_font_change
from utils.resource_loader import resource_path

from .service import ImageProperties, ImagePropertyRow, ImagePropertySection


class ImagePropertiesDialog(ThemedDialog):
    def __init__(
        self,
        properties: ImageProperties,
        *,
        parent=None,
        current_language: str | None = None,
        tr_func=None,
    ) -> None:
        super().__init__(parent)
        self.properties = properties
        self.current_language = current_language or get_current_language() or "en"
        self.tr = tr_func if callable(tr_func) else app_tr
        self.theme_manager = ThemeManager.get_instance()

        self.setObjectName("ImagePropertiesDialog")
        self.setWindowIcon(QIcon(resource_path("resources/icons/icon.png")))
        self.setWindowTitle(self._tr("image_properties.title", "Properties"))
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.setSizeGripEnabled(True)
        self.properties_section_frames: list[QFrame] = []

        self._init_ui()
        self.install_dialog_geometry(self._apply_dialog_geometry)
        self.mark_theme_ui_ready()

        from shared_toolkit.ui.decorate_dialog import decorate_dialog

        decorate_dialog(self, title=self._tr("image_properties.title", "Properties"))
        # CSD adjustSize + deferred geometry can land after first map; re-apply
        # once so section frames stretch across the scroll content.
        QTimer.singleShot(0, self._finalize_layout_and_size)

    def _apply_dialog_geometry(self) -> None:
        apply_image_properties_dialog_geometry(self)

    def _finalize_layout_and_size(self) -> None:
        apply_image_properties_dialog_geometry(self)
        try:
            from sli_ui_toolkit.ui.windows.csd_helpers import sync_csd_chrome

            sync_csd_chrome(self)
        except Exception:
            pass

    def showEvent(self, event) -> None:
        super().showEvent(event)
        # First paint can race deferred geometry; activate stretch on show.
        QTimer.singleShot(0, self._finalize_layout_and_size)

    def changeEvent(self, event):
        handle_application_font_change(self, event)
        super().changeEvent(event)

    def update_language(self, language: str) -> None:
        self.current_language = language or "en"
        self.setWindowTitle(self._tr("image_properties.title", "Properties"))
        self.copy_all_button.setText(
            self._tr("image_properties.copy_all", "Copy all")
        )
        self.close_button.setText(self._tr("image_properties.close", "Close"))
        self._apply_dialog_geometry()

    def _init_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        scroll = OverlayScrollArea(self)
        scroll.set_reserve_scrollbar_space(False)
        scroll.set_corner_radius(0)

        content = QWidget(scroll)
        self.properties_scroll_content = content
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(10)

        for section in self.properties.sections:
            if section.rows:
                frame = self._build_section(section)
                self.properties_section_frames.append(frame)
                content_layout.addWidget(frame)
        content_layout.addStretch()

        scroll.setWidget(content)
        root.addWidget(scroll, 1)

        actions = QWidget(self)
        self.properties_actions = actions
        action_layout = QGridLayout(actions)
        action_layout.setContentsMargins(0, 0, 0, 0)
        action_layout.setHorizontalSpacing(8)
        action_layout.setColumnStretch(0, 1)

        self.copy_all_button = Button(
            text=self._tr("image_properties.copy_all", "Copy all"),
            variant="surface",
            parent=actions,
        )
        self.copy_all_button.setMinimumSize(110, 36)
        self.close_button = Button(
            text=self._tr("image_properties.close", "Close"),
            variant="surface",
            parent=actions,
        )
        self.close_button.setMinimumSize(100, 36)
        self.copy_all_button.clicked.connect(self._copy_all)
        self.close_button.clicked.connect(self.accept)

        action_layout.addWidget(self.copy_all_button, 0, 1)
        action_layout.addWidget(self.close_button, 0, 2)
        root.addWidget(actions)

    def _build_section(self, section: ImagePropertySection) -> QFrame:
        frame = QFrame(self)
        frame.setObjectName("ImagePropertiesSection")
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 8, 10, 10)
        layout.setSpacing(6)

        header = Label(
            self._tr(section.title_key, section.fallback_title),
            variant="group-title",
            parent=frame,
        )
        layout.addWidget(header)

        grid_host = QWidget(frame)
        grid = QGridLayout(grid_host)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(5)
        grid.setColumnMinimumWidth(0, 130)
        grid.setColumnStretch(1, 1)

        for row_index, row in enumerate(section.rows):
            key_label = Label(
                self._tr(row.label_key, row.fallback_label),
                variant="caption",
                parent=grid_host,
            )
            key_label.setAlignment(
                Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
            )
            value_label = Label(
                self._row_value(row),
                variant="body",
                parent=grid_host,
            )
            value_label.setWordWrap(True)
            value_label.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
            value_label.setCursor(Qt.CursorShape.ArrowCursor)
            value_label.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Preferred,
            )
            grid.addWidget(key_label, row_index, 0)
            grid.addWidget(value_label, row_index, 1)

        layout.addWidget(grid_host)
        return frame

    def _copy_all(self) -> None:
        QGuiApplication.clipboard().setText(
            self.properties.as_plain_text(lambda key: self._tr(key, key))
        )

    def _row_value(self, row: ImagePropertyRow) -> str:
        if row.value_key:
            return self._tr(row.value_key, row.fallback_value or row.value)
        return row.value or "-"

    def _tr(self, key: str, default: str) -> str:
        text = self.tr(key, self.current_language)
        return default if text == key else text
