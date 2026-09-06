from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication, QIcon
from shared_toolkit.ui.themed_dialog import ThemedDialog
from PySide6.QtWidgets import (
    QGridLayout,
    QVBoxLayout,
    QWidget,
)
from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.managers import scaled_px
from sli_ui_toolkit.widgets import (
    Button,
    ContextMenuAction,
    ContextMenuSeparator,
    HelpDocumentView,
    OverlayScrollArea,
)

from plugins.image_properties.layout_geometry import apply_image_properties_dialog_geometry
from plugins.image_properties.render import build_property_blocks
from resources.translations import get_current_language
from resources.translations import tr as app_tr
from shared_toolkit.ui.layout_sizing import handle_application_font_change
from ui.context_menu.manager import open_context_menu_entries
from ui.icon_manager import AppIcon, get_app_icon
from utils.resource_loader import resource_path

from .service import ImageProperties


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

        self._init_ui()
        self.install_dialog_geometry(self._apply_dialog_geometry)
        self.mark_theme_ui_ready()

        from shared_toolkit.ui.decorate_dialog import decorate_dialog, install_dialog_help_menu

        decorate_dialog(self, title=self._tr("image_properties.title", "Properties"))
        install_dialog_help_menu(self, page="image_properties")
        # CSD adjustSize + deferred geometry can land after first map; re-apply
        # once so the document canvas stretches across the scroll content.
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
        # Apply the computed geometry before the first paint — showEvent runs
        # before the dialog's first frame is drawn, so the deferred 0-timer
        # (scheduled in __init__) would otherwise land after a visible frame
        # at the CSD-adjustSize size. The __init__ timer stays as the
        # pre-show (already-sized) fallback.
        self._finalize_layout_and_size()

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
        self._render_content()
        self._apply_dialog_geometry()

    def _init_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        scroll = OverlayScrollArea(self)
        scroll.set_reserve_scrollbar_space(False)
        scroll.set_corner_radius(0)

        self.properties_document = HelpDocumentView(parent=scroll, show_toc=False)
        self.properties_scroll_content = self.properties_document
        self.properties_document.textContextMenuRequested.connect(
            self._on_text_context_menu
        )
        self._render_content()

        scroll.setWidget(self.properties_document)
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
        self.copy_all_button.setMinimumSize(scaled_px(110), scaled_px(36))
        self.close_button = Button(
            text=self._tr("image_properties.close", "Close"),
            variant="surface",
            parent=actions,
        )
        self.close_button.setMinimumSize(scaled_px(100), scaled_px(36))
        self.copy_all_button.clicked.connect(self._copy_all)
        self.close_button.clicked.connect(self.accept)

        action_layout.addWidget(self.copy_all_button, 0, 1)
        action_layout.addWidget(self.close_button, 0, 2)
        root.addWidget(actions)

    def _render_content(self) -> None:
        self.properties_document.set_blocks(
            build_property_blocks(self.properties, self._tr)
        )

    def _copy_all(self) -> None:
        QGuiApplication.clipboard().setText(
            self.properties.as_plain_text(lambda key: self._tr(key, key))
        )

    def _on_text_context_menu(self, global_pos) -> None:
        document = self.properties_document
        has_selection = bool(document.selected_plain_text().strip())
        entries: list[ContextMenuAction | ContextMenuSeparator] = [
            ContextMenuAction(
                "image_properties.text.copy",
                self._tr("action.context_copy", "Copy"),
                icon=get_app_icon("copy.svg"),
                shortcut="Ctrl+C",
                enabled=has_selection,
            ),
            ContextMenuSeparator(),
            ContextMenuAction(
                "image_properties.text.select_all",
                self._tr("action.context_select_all", "Select all"),
                icon=AppIcon.TEXT_MANIPULATOR,
                shortcut="Ctrl+A",
            ),
        ]

        def on_triggered(action_id: str, _data: object) -> None:
            if action_id == "image_properties.text.copy":
                text = document.selected_plain_text()
                if text:
                    QGuiApplication.clipboard().setText(text)
            elif action_id == "image_properties.text.select_all":
                document.select_all_text()

        open_context_menu_entries(
            source_widget=self,
            global_pos=global_pos,
            entries=tuple(entries),
            key=("image_properties_text", id(document)),
            on_triggered=on_triggered,
        )

    def _tr(self, key: str, default: str) -> str:
        text = self.tr(key, self.current_language)
        return default if text == key else text