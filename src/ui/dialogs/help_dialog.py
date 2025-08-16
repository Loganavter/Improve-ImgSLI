from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QListWidget,
    QStackedWidget,
    QLabel,
    QFrame,
    QListWidgetItem,
    QScrollArea,
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QFontMetrics, QIcon

from utils.resource_loader import resource_path
from core.theme import ThemeManager
from resources.translations import tr

class HelpDialog(QDialog):
    def __init__(self, current_language, parent=None):
        super().__init__(parent)
        self.setWindowIcon(QIcon(resource_path("resources/icons/icon.png")))
        self.setObjectName("HelpDialog")
        self.current_language = current_language
        self.theme_manager = ThemeManager.get_instance()

        self.setWindowTitle(tr("Improve ImgSLI Help", self.current_language))

        self.setWindowFlags(
            Qt.WindowType.Window | Qt.WindowType.WindowTitleHint | Qt.WindowType.WindowCloseButtonHint
        )
        self.setSizeGripEnabled(True)
        self.resize(800, 600)
        self.setMinimumSize(640, 480)

        self._setup_ui()
        self._populate_content()
        self._apply_styles()

        self.theme_manager.theme_changed.connect(self._apply_styles)

    def _setup_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.nav_widget = QListWidget()
        self.nav_widget.setFrameShape(QFrame.Shape.NoFrame)
        self.nav_widget.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.nav_widget.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.nav_widget.currentRowChanged.connect(self.change_page)

        self.content_stack = QStackedWidget()
        self.content_stack.setFrameShape(QFrame.Shape.NoFrame)
        self.content_stack.setSizePolicy(
            self.content_stack.sizePolicy().horizontalPolicy(),
            self.content_stack.sizePolicy().verticalPolicy(),
        )

        self.scroll_area = QScrollArea()
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_area.setWidget(self.content_stack)

        main_layout.addWidget(self.nav_widget)
        main_layout.addWidget(self.scroll_area, 1)

    def _update_nav_width(self):
        max_text_width = 0
        for i in range(self.nav_widget.count()):
            item = self.nav_widget.item(i)
            text = item.text()
            text_width = QFontMetrics(self.nav_widget.font()).horizontalAdvance(text)
            max_text_width = max(max_text_width, text_width)
        self.nav_widget.setFixedWidth(max(180, max_text_width + 32))

    def _populate_content(self):
        sections = [
            ("Help Section: Introduction", "help_intro_html"),
            ("Help Section: File Management", "help_files_html"),
            ("Help Section: Basic Comparison", "help_comparison_html"),
            ("Help Section: Magnifier Tool", "help_magnifier_html"),
            ("Help Section: Exporting Results", "help_export_html"),
            ("Help Section: Settings", "help_settings_html"),
            ("Help Section: Hotkeys", "help_hotkeys_html"),
        ]

        self._content_keys = []
        for title_key, content_key in sections:
            self._add_section(title_key, content_key)
            self._content_keys.append(content_key)

        if self.nav_widget.count() > 0:
            self.nav_widget.setCurrentRow(0)

        self._update_nav_width()

    def _add_section(self, title_key: str, content_key: str):
        title = tr(title_key, self.current_language)
        nav_item = QListWidgetItem(title, self.nav_widget)
        nav_item.setSizeHint(QSize(200, 35))

        content_page = QLabel()
        content_page.setMargin(25)
        content_page.setWordWrap(True)
        content_page.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
        )
        content_page.setTextFormat(Qt.TextFormat.RichText)
        content_page.setOpenExternalLinks(True)

        html_content = tr(content_key, self.current_language)

        content_page.setText(html_content)

        self.content_stack.addWidget(content_page)

    def change_page(self, index: int):
        self.content_stack.setCurrentIndex(index)

    def _apply_styles(self):

        self.style().unpolish(self)
        self.style().polish(self)

        tm = self.theme_manager
        text_color = tm.get_color("dialog.text").name()
        separator_color = tm.get_color("help.separator").name()
        code_bg_color = tm.get_color("help.code.background").name()
        bold_color = text_color

        content_wrapper_style = f"""
        <style>
            body {{ font-size: 14px; color: {text_color}; }}
            h2 {{ margin-bottom: 8px; border-bottom: 1px solid {separator_color}; padding-bottom: 4px; }}
            h3 {{ margin: 12px 0 6px 0; }}
            ul {{ margin: 0; padding-left: 20px; }}
            li {{ margin-bottom: 5px; }}
            b, strong {{ color: {bold_color}; }}
        </style>
        """
        for i in range(self.content_stack.count()):
            page = self.content_stack.widget(i)
            if isinstance(page, QLabel):
                key = self._content_keys[i] if hasattr(self, '_content_keys') and i < len(self._content_keys) else None
                html_content = tr(key, self.current_language) if key else ""
                page.setText(content_wrapper_style + html_content)

    def update_language(self, new_language: str):
        self.current_language = new_language
        self.setWindowTitle(tr("Improve ImgSLI Help", self.current_language))
        self.nav_widget.clear()

        while self.content_stack.count() > 0:
            w = self.content_stack.widget(0)
            self.content_stack.removeWidget(w)
            w.deleteLater()
        self._populate_content()
        self._apply_styles()
