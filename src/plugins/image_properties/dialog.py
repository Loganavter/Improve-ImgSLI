from __future__ import annotations

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QGuiApplication, QIcon
from shared_toolkit.ui.themed_dialog import ThemedDialog
from PySide6.QtWidgets import (
    QGridLayout,
    QVBoxLayout,
    QWidget,
)
from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.managers import scaled_px
from sli_ui_toolkit.ui.managers import connect_ui_metrics
from sli_ui_toolkit.ui.managers.ui_metrics import AXIS_SCALE
from sli_ui_toolkit.widgets import (
    Button,
    ContextMenuAction,
    ContextMenuSeparator,
    OverlayScrollArea,
    Text,
)

from plugins.image_properties.layout_geometry import apply_image_properties_dialog_geometry
from plugins.image_properties.render import build_property_blocks
from resources.translations import get_current_language
from resources.translations import tr as app_tr
from shared_toolkit.ui.layout_sizing import handle_application_font_change
from ui.context_menu.manager import open_context_menu_entries
from ui.icon_manager import AppIcon, themed_icon
from utils.resource_loader import resource_path

from .service import ImageProperties

#: Design px of the dialog's root chrome. Resolved through ``scaled_px`` at
#: use time (never at import) and re-resolved on a live ``UiScale`` change.
_ROOT_MARGIN_PX = 12
_ROOT_SPACING_PX = 10
#: Page padding around the property document (``HelpDocumentView``'s root
#: layout margins: left, top, right, bottom).
_DOC_PAGE_MARGINS_PX = (20, 16, 20, 24)


def _page_margins() -> tuple[int, int, int, int]:
    left, top, right, bottom = _DOC_PAGE_MARGINS_PX
    return (
        scaled_px(left),
        scaled_px(top),
        scaled_px(right),
        scaled_px(bottom),
    )


class _PropertiesDocumentPage(QWidget):
    """Scroll content host: page padding + the painted ``Text`` document.

    ``HelpDocumentView`` reported its **live width** as ``sizeHint`` and the
    dialog geometry recipe reads that (``compute_image_properties_dialog_size``
    → ``_size_hint`` over the scroll content); ``Text`` deliberately reports
    ``QSize(0, height)`` as a plain widget. The host reproduces the measurable
    contract while owning the padding the old view laid out itself.
    """

    def __init__(self, text: Text, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # Named ``text`` (not ``document``): the store's session "document"
        # mirror attribute name is contract-reserved for its owner.
        self.text = text
        text.setParent(self)
        self._layout = QVBoxLayout(self)
        self._layout.setSpacing(0)
        self._layout.addWidget(text)
        self._apply_metrics()
        connect_ui_metrics(
            self, self._on_metrics_changed, axes=frozenset({AXIS_SCALE})
        )

    def _apply_metrics(self) -> None:
        self._layout.setContentsMargins(*_page_margins())

    def _on_metrics_changed(self, *_args: object) -> None:
        self._apply_metrics()
        self.updateGeometry()
        self.text.updateGeometry()

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt API
        hint = self.text.size_hint_from_content()
        width = self.width() if self.width() > 1 else hint.width()
        _, top, _, bottom = _page_margins()
        return QSize(max(0, width), max(0, hint.height() + top + bottom))


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
        # Never assign to ``self.tr`` — QObject.tr() is Qt's own API and
        # shadowing it makes translations look like raw keys.
        self._tr_func = tr_func if callable(tr_func) else app_tr
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
        self._connect_design_metrics()
        # Keyboard navigation: the dialog had no section at all (see
        # plugins/image_properties/navigation.py).
        from plugins.image_properties.navigation import (
            register_image_properties_navigation,
        )

        register_image_properties_navigation(self)
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

    @staticmethod
    def _apply_root_design_metrics(root: QVBoxLayout) -> None:
        """Resolve the root layout's design px at use time (not at import)."""
        root.setContentsMargins(
            scaled_px(_ROOT_MARGIN_PX),
            scaled_px(_ROOT_MARGIN_PX),
            scaled_px(_ROOT_MARGIN_PX),
            scaled_px(_ROOT_MARGIN_PX),
        )
        root.setSpacing(scaled_px(_ROOT_SPACING_PX))

    def _connect_design_metrics(self) -> None:
        """Re-resolve the root chrome when the UI scale changes live.

        The dialog's own geometry pass re-derives its size on a theme/font
        change, but the root layout's margins/spacing are design px this
        dialog owns — without a subscription they stay at the factor they
        were built with.
        """
        from sli_ui_toolkit.ui.managers import connect_ui_metrics
        from sli_ui_toolkit.ui.managers.ui_metrics import AXIS_SCALE

        connect_ui_metrics(
            self, self._on_design_metrics_changed, axes=frozenset({AXIS_SCALE})
        )

    def _on_design_metrics_changed(self, *_args) -> None:
        root = self.layout()
        if root is not None:
            self._apply_root_design_metrics(root)
        self.updateGeometry()

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
        self._apply_root_design_metrics(root)

        scroll = OverlayScrollArea(self)
        scroll.set_reserve_scrollbar_space(False)
        scroll.set_corner_radius(0)

        self.properties_document = Text(mode="document", parent=scroll)
        self.properties_document.set_panel_fill(True)
        self.properties_document.textContextMenuRequested.connect(
            self._on_text_context_menu
        )
        self.properties_scroll_content = _PropertiesDocumentPage(
            self.properties_document, scroll
        )
        self._render_content()

        scroll.setWidget(self.properties_scroll_content)
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
                icon=themed_icon("copy.svg"),
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
        text = self._tr_func(key, self.current_language)
        return default if text == key else text