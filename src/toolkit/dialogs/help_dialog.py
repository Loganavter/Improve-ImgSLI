from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QFontMetrics, QIcon
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QScrollArea,
    QStackedWidget,
)
import os

import logging
logging.getLogger('markdown').setLevel(logging.WARNING)
logging.getLogger('markdown.extensions').setLevel(logging.WARNING)
logging.getLogger('markdown.extensions.md_in_html').setLevel(logging.WARNING)
logging.getLogger('markdown.extensions.extra').setLevel(logging.WARNING)
logging.getLogger('markdown.extensions.sane_lists').setLevel(logging.WARNING)
logging.getLogger('markdown.extensions.smarty').setLevel(logging.WARNING)
logging.getLogger('markdown.extensions.nl2br').setLevel(logging.WARNING)

from markdown import markdown

from toolkit.managers.theme_manager import ThemeManager
from toolkit.widgets.atomic.minimalist_scrollbar import (
    MinimalistScrollBar,
)
from utils.resource_loader import resource_path
from resources.translations import tr

class CurrentPageStackedWidget(QStackedWidget):

    def sizeHint(self):
        current_widget = self.currentWidget()
        if current_widget:
            return current_widget.sizeHint()
        return super().sizeHint()

    def minimumSizeHint(self):
        current_widget = self.currentWidget()
        if current_widget:
            return current_widget.minimumSizeHint()
        return super().minimumSizeHint()

class HelpDialog(QDialog):
    def __init__(self, sections: list, current_language, app_name: str, parent=None):
        super().__init__(parent)
        self.setWindowIcon(QIcon(resource_path("resources/icons/icon.png")))
        self.setObjectName("HelpDialog")
        self.current_language = current_language
        self.app_name = app_name
        self.theme_manager = ThemeManager.get_instance()

        self._md_cache: dict[str, dict[str, str]] = {}
        self._title_keys: list[str] = []

        self.setWindowTitle(tr("help.help", language=self.current_language))

        self.setWindowFlags(
            Qt.WindowType.Window | Qt.WindowType.WindowTitleHint | Qt.WindowType.WindowCloseButtonHint
        )
        self.setSizeGripEnabled(True)
        self.resize(800, 600)
        self.setMinimumSize(640, 480)

        self._setup_ui()
        self._populate_content(sections)
        self._apply_styles()

        self.theme_manager.theme_changed.connect(self._apply_styles)

    def _setup_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.nav_widget = QListWidget()
        self.nav_widget.setFrameShape(QFrame.Shape.NoFrame)
        self.nav_widget.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.nav_widget.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        nav_scrollbar = MinimalistScrollBar()
        self.nav_widget.setVerticalScrollBar(nav_scrollbar)

        self.nav_widget.currentRowChanged.connect(self.change_page)

        self._pages = []

        self.scroll_area = QScrollArea()
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        minimalist_scrollbar = MinimalistScrollBar()
        self.scroll_area.setVerticalScrollBar(minimalist_scrollbar)

        main_layout.addWidget(self.nav_widget)
        main_layout.addWidget(self.scroll_area, 1)

    def _update_nav_width(self):
        max_text_width = 0
        for i in range(self.nav_widget.count()):
            if i < len(self._title_keys):
                title_key = self._title_keys[i]

                max_width_for_item = 0
                for lang in ["en", "ru", "zh", "pt_BR"]:
                    try:
                        text = tr(title_key, language=lang)
                        text_width = QFontMetrics(self.nav_widget.font()).horizontalAdvance(text)
                        max_width_for_item = max(max_width_for_item, text_width)
                    except Exception:
                        try:
                            text = tr(title_key, language="en")
                            text_width = QFontMetrics(self.nav_widget.font()).horizontalAdvance(text)
                            max_width_for_item = max(max_width_for_item, text_width)
                        except Exception:
                            text_width = QFontMetrics(self.nav_widget.font()).horizontalAdvance(title_key)
                            max_width_for_item = max(max_width_for_item, text_width)
                max_text_width = max(max_text_width, max_width_for_item)
            else:

                item = self.nav_widget.item(i)
                text = item.text()
                text_width = QFontMetrics(self.nav_widget.font()).horizontalAdvance(text)
                max_text_width = max(max_text_width, text_width)

        self.nav_widget.setFixedWidth(max(180, max_text_width + 32))

    def _populate_content(self, sections):
        self._content_keys = []
        self._title_keys = []

        for page in self._pages:
            page.deleteLater()
        self._pages.clear()

        for title_key, section_id in sections:
            self._add_section(title_key, section_id)
            self._content_keys.append(section_id)
            self._title_keys.append(title_key)

        if self.nav_widget.count() > 0:
            self.nav_widget.setCurrentRow(0)

        self._update_nav_width()

    def _add_section(self, title_key: str, section_id: str):
        try:
            title = tr(title_key, language=self.current_language)
        except Exception:
            title = title_key

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

        html_content = self.load_section_md(self.current_language, section_id)
        content_page.setText(html_content)

        self._pages.append(content_page)

    def _normalize_markdown_lists(self, md_text: str) -> str:
        lines = md_text.splitlines()
        out: list[str] = []
        for i, line in enumerate(lines):
            stripped = line.lstrip()
            is_list_item = (
                stripped.startswith("- ") or
                stripped.startswith("* ") or
                stripped.startswith("+ ") or
                (len(stripped) > 2 and stripped[0].isdigit() and stripped[1:3] == ". ")
            )
            prev_is_list = False
            if out:
                prev_stripped = out[-1].lstrip()
                prev_is_list = (
                    prev_stripped.startswith("- ") or
                    prev_stripped.startswith("* ") or
                    prev_stripped.startswith("+ ") or
                    (len(prev_stripped) > 2 and prev_stripped[0].isdigit() and prev_stripped[1:3] == ". ")
                )

            if is_list_item and out and len(out[-1].strip()) > 0 and not prev_is_list:
                out.append("")
            out.append(line)
        return "\n".join(out)

    def _fallback_plainlist_to_html(self, md_text: str) -> str:
        def is_bullet(s: str) -> bool:
            s = s.lstrip()
            if s.startswith("- ") or s.startswith("* ") or s.startswith("+ "):
                return True

            i = 0
            while i < len(s) and s[i].isdigit():
                i += 1
            if i > 0 and i + 1 < len(s) and s[i] == "." and s[i + 1] == " ":
                return True
            return False

        html_parts: list[str] = []
        in_list = False
        list_tag = "ul"
        for raw in md_text.splitlines():
            line = raw.rstrip("\n")
            if is_bullet(line):
                s = line.lstrip()

                i = 0
                while i < len(s) and s[i].isdigit():
                    i += 1
                is_ordered = (i > 0 and i + 1 < len(s) and s[i] == "." and s[i + 1] == " ")

                desired_tag = "ol" if is_ordered else "ul"
                if not in_list or list_tag != desired_tag:
                    if in_list:
                        html_parts.append(f"</{list_tag}>")
                    list_tag = desired_tag
                    in_list = True
                    html_parts.append(f"<{list_tag}>")

                if list_tag == "ul":

                    content = s[2:] if len(s) >= 2 else ""
                else:

                    j = 0
                    while j < len(s) and s[j].isdigit():
                        j += 1
                    content = s[j + 2:] if j + 2 <= len(s) else ""

                html_parts.append(f"<li>{content}</li>")
            else:

                if in_list:
                    html_parts.append(f"</{list_tag}>")
                    in_list = False
                if line.strip():
                    html_parts.append(f"<p>{line}</p>")
                else:
                    html_parts.append("")
        if in_list:
            html_parts.append(f"</{list_tag}>")
        return "\n".join(html_parts)

    def load_section_md(self, language: str, section_id: str) -> str:

        try:
            lang_norm = str(language) if language is not None else "en"
        except Exception:
            lang_norm = "en"
        lang_norm = lang_norm.strip()
        base = lang_norm.split("_")[0].lower() if "_" in lang_norm else lang_norm.lower()
        if base == "pt":
            norm_lang = "pt_BR"
        elif base in ("zh", "zh-cn", "zh_cn", "zh-hans", "zh-hant"):
            norm_lang = "zh"
        elif base in ("ru", "en"):
            norm_lang = base
        else:

            norm_lang = "en"

        lang_cache = self._md_cache.get(language, {})
        cached = lang_cache.get(section_id)
        if cached is not None:
            return cached

        html_content = ""
        try:
            md_path = resource_path(f"resources/help/{norm_lang}/{section_id}.md")
            if os.path.isfile(md_path):
                with open(md_path, "r", encoding="utf-8") as f:
                    md_text = f.read()
                md_text = self._normalize_markdown_lists(md_text)
                html_content = markdown(md_text, extensions=["extra", "sane_lists", "smarty", "nl2br"])

                if ("<ul" not in html_content and "<ol" not in html_content) and any(
                    l.lstrip().startswith(("- ", "* ", "+ ")) or
                    (l.lstrip()[:1].isdigit() and ". " in l.lstrip())
                    for l in md_text.splitlines()
                ):
                    html_content = self._fallback_plainlist_to_html(md_text)
            else:
                raise FileNotFoundError(md_path)
        except Exception:

            try:
                en_path = resource_path(f"resources/help/en/{section_id}.md")
                if os.path.isfile(en_path):
                    with open(en_path, "r", encoding="utf-8") as f:
                        md_text = f.read()
                    md_text = self._normalize_markdown_lists(md_text)
                    html_content = markdown(md_text, extensions=["extra", "sane_lists", "smarty", "nl2br"])
                    if ("<ul" not in html_content and "<ol" not in html_content) and any(
                        l.lstrip().startswith(("- ", "* ", "+ ")) or
                        (l.lstrip()[:1].isdigit() and ". " in l.lstrip())
                        for l in md_text.splitlines()
                    ):
                        html_content = self._fallback_plainlist_to_html(md_text)
                else:
                    raise FileNotFoundError(en_path)
            except Exception:

                legacy_map = {
                    "introduction": "help_intro_html",
                    "files": "help_files_html",
                    "conversion": "help_conversion_html",
                    "analysis": "help_analysis_html",
                    "ai": "help_ai_html",
                    "export": "help_export_html",
                }
                legacy_key = legacy_map.get(section_id)
                if legacy_key:
                    try:
                        html_content = tr(legacy_key, language=language)
                    except Exception:
                        html_content = ""
                else:
                    html_content = ""

        if language not in self._md_cache:
            self._md_cache[language] = {}
        self._md_cache[language][section_id] = html_content
        return html_content

    def change_page(self, index: int):
        if index < 0 or index >= len(self._pages):
            return

        old_widget = self.scroll_area.takeWidget()
        if old_widget is not None:

            old_widget.hide()
            old_widget.setParent(None)

        page = self._pages[index]
        self.scroll_area.setWidget(page)
        page.show()
        page.adjustSize()
        self.scroll_area.verticalScrollBar().setValue(0)

    def _apply_styles(self):
        self.theme_manager.apply_theme_to_dialog(self)

        tm = self.theme_manager
        text_color = tm.get_color("dialog.text").name()
        separator_color = tm.get_color("help.separator").name()
        dialog_bg_color = tm.get_color("dialog.background").name()
        bold_color = text_color

        def _hex_to_rgb(h: str):
            h = h.lstrip("#")
            if len(h) == 8:

                h = h[2:]
            r = int(h[0:2], 16)
            g = int(h[2:4], 16)
            b = int(h[4:6], 16)
            return r, g, b

        def _rgb_to_hex(r: int, g: int, b: int) -> str:
            r = max(0, min(255, r))
            g = max(0, min(255, g))
            b = max(0, min(255, b))
            return f"#{r:02X}{g:02X}{b:02X}"

        def _luminance(r: int, g: int, b: int) -> float:

            return 0.2126 * r + 0.7152 * g + 0.0722 * b

        def _shade(r: int, g: int, b: int, amount: float) -> tuple[int, int, int]:

            if amount >= 0:
                nr = r + (255 - r) * amount
                ng = g + (255 - g) * amount
                nb = b + (255 - b) * amount
            else:
                nr = r * (1 + amount)
                ng = g * (1 + amount)
                nb = b * (1 + amount)
            return int(round(nr)), int(round(ng)), int(round(nb))

        bg_r, bg_g, bg_b = _hex_to_rgb(dialog_bg_color)
        bg_lum = _luminance(bg_r, bg_g, bg_b)

        shade_amount = -0.08 if bg_lum > 128 else 0.12
        code_bg_r, code_bg_g, code_bg_b = _shade(bg_r, bg_g, bg_b, shade_amount)
        code_bg_color_solid = _rgb_to_hex(code_bg_r, code_bg_g, code_bg_b)

        border_r, border_g, border_b = _shade(bg_r, bg_g, bg_b, -0.18 if bg_lum > 128 else 0.18)
        code_border_color = _rgb_to_hex(border_r, border_g, border_b)

        content_wrapper_style = f"""
        <style>
            body {{ font-size: 14px; color: {text_color}; }}
            h2 {{ margin-bottom: 8px; border-bottom: 1px solid {separator_color}; padding-bottom: 4px; }}
            h3 {{ margin: 12px 0 6px 0; }}
            ul, ol {{ margin: 8px 0; padding-left: 24px; }}
            li {{ margin: 0 0 6px 0; display: list-item; }}
            b, strong {{ color: {bold_color}; }}
            code {{
                background-color: {code_bg_color_solid};
                color: {text_color};
                padding: 2px 4px;
                border-radius: 4px;
                border: 1px solid {code_border_color};
            }}
            pre {{
                background-color: {code_bg_color_solid};
                color: {text_color};
                padding: 10px 12px;
                border-radius: 6px;
                white-space: pre-wrap;
                border: 1px solid {code_border_color};
            }}
            pre code {{
                background-color: transparent;  /* avoid double background */
                color: {text_color};
                padding: 0;
                border: none;
            }}
            /* Optional: keyboard-like styling if <kbd> appears in future */
            kbd {{
                background-color: {code_bg_color_solid};
                color: {text_color};
                padding: 2px 6px;
                border-radius: 4px;
                border: 1px solid {code_border_color};
                font-family: inherit;
            }}
        </style>
        """
        for i in range(len(self._pages)):
            page = self._pages[i]
            section_id = self._content_keys[i] if hasattr(self, '_content_keys') and i < len(self._content_keys) else None
            html_content = ""
            if section_id:
                lang_cache = self._md_cache.get(self.current_language, {})
                html_content = lang_cache.get(section_id)
                if html_content is None:
                    html_content = self.load_section_md(self.current_language, section_id)
            page.setText(content_wrapper_style + (html_content or ""))

    def update_language(self, new_language: str):
        self.current_language = new_language
        self.setWindowTitle(tr("help.help", language=self.current_language))

        if self.current_language in self._md_cache:
            del self._md_cache[self.current_language]

        self.nav_widget.clear()

        old = self.scroll_area.takeWidget()
        if old is not None:
            old.deleteLater()

        sections = []
        for i in range(len(self._content_keys)):
            if i < len(self._title_keys):
                sections.append((self._title_keys[i], self._content_keys[i]))

        self._populate_content(sections)
        self._apply_styles()

