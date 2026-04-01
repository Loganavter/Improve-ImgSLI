from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QFontMetrics, QIcon
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QLabel,
    QListWidgetItem,
    QScrollArea,
    QStackedWidget,
)
from markdown import markdown

from shared_toolkit.ui.managers.theme_manager import ThemeManager
from shared_toolkit.ui.widgets.atomic.minimalist_scrollbar import MinimalistScrollBar
from shared_toolkit.ui.widgets.composite import SidebarDialogShell
from shared_toolkit.utils.paths import resource_path
from ui.icon_manager import AppIcon, get_app_icon

logging.getLogger("markdown").setLevel(logging.WARNING)
logging.getLogger("markdown.extensions").setLevel(logging.WARNING)
logging.getLogger("markdown.extensions.md_in_html").setLevel(logging.WARNING)
logging.getLogger("markdown.extensions.extra").setLevel(logging.WARNING)
logging.getLogger("markdown.extensions.sane_lists").setLevel(logging.WARNING)
logging.getLogger("markdown.extensions.smarty").setLevel(logging.WARNING)
logging.getLogger("markdown.extensions.nl2br").setLevel(logging.WARNING)

try:
    from resources.translations import tr
except ImportError:

    def tr(key, language=None):
        return key

@dataclass(frozen=True)
class HelpSection:
    order: int
    slug: str
    title: str
    body_md: str

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
    _SECTION_PATTERN = re.compile(r"^(?P<order>\d{3})_(?P<slug>.+)\.md$")

    def __init__(self, current_language: str, app_name: str, parent=None):
        super().__init__(parent)
        self.setWindowIcon(QIcon(get_app_icon(AppIcon.HELP)))
        self.setObjectName("HelpDialog")
        self.current_language = current_language
        self.app_name = app_name
        self.theme_manager = ThemeManager.get_instance()
        self._sections_cache: dict[str, tuple[HelpSection, ...]] = {}
        self._pages: list[QLabel] = []
        self._sections: tuple[HelpSection, ...] = ()

        self.setWindowTitle(tr("help.help", language=self.current_language))
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.setSizeGripEnabled(True)
        self.resize(800, 600)
        self.setMinimumSize(640, 480)

        self._setup_ui()
        self._reload_sections()
        self._apply_styles()
        self.theme_manager.theme_changed.connect(self._apply_styles)

    def _setup_ui(self) -> None:
        from PyQt6.QtWidgets import QHBoxLayout

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.shell = SidebarDialogShell(content_margins=(0, 0, 0, 0), content_spacing=0)
        self.nav_widget = self.shell.sidebar
        self.nav_widget.enable_minimal_scrollbar()
        self.nav_widget.currentRowChanged.connect(self.change_page)

        self.scroll_area = QScrollArea()
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_area.setVerticalScrollBar(MinimalistScrollBar())

        self.shell.pages_stack.hide()
        self.shell.content_layout.addWidget(self.scroll_area, 1)
        main_layout.addWidget(self.shell)

    def _reload_sections(self) -> None:
        self._sections = self._discover_sections(self.current_language)
        self.nav_widget.clear()

        old = self.scroll_area.takeWidget()
        if old is not None:
            old.deleteLater()

        for page in self._pages:
            page.deleteLater()
        self._pages.clear()

        for section in self._sections:
            nav_item = QListWidgetItem(section.title, self.nav_widget)
            nav_item.setSizeHint(QSize(200, 35))

            content_page = QLabel()
            content_page.setMargin(25)
            content_page.setWordWrap(True)
            content_page.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
            content_page.setTextFormat(Qt.TextFormat.RichText)
            content_page.setOpenExternalLinks(True)
            self._pages.append(content_page)

        if self.nav_widget.count() > 0:
            self.nav_widget.setCurrentRow(0)

        self._update_nav_width()
        self._apply_styles()

    def _discover_sections(self, language: str) -> tuple[HelpSection, ...]:
        cached = self._sections_cache.get(language)
        if cached is not None:
            return cached

        lang_dir = self._resolve_help_dir(language)
        sections = self._read_sections_from_dir(lang_dir)

        if not sections and lang_dir != self._resolve_help_dir("en"):
            sections = self._read_sections_from_dir(self._resolve_help_dir("en"))

        self._sections_cache[language] = sections
        return sections

    def _resolve_help_dir(self, language: str) -> str:
        try:
            lang_norm = str(language).strip()
        except Exception:
            lang_norm = "en"
        base = lang_norm.split("_")[0].lower() if "_" in lang_norm else lang_norm.lower()
        if base == "pt":
            lang_code = "pt_BR"
        elif base.startswith("zh"):
            lang_code = "zh"
        elif base in ("ru", "en"):
            lang_code = base
        else:
            lang_code = "en"
        return resource_path(f"resources/help/{lang_code}")

    def _read_sections_from_dir(self, directory: str) -> tuple[HelpSection, ...]:
        if not os.path.isdir(directory):
            return ()

        sections: list[HelpSection] = []
        for filename in sorted(os.listdir(directory)):
            match = self._SECTION_PATTERN.match(filename)
            if not match:
                continue
            full_path = os.path.join(directory, filename)
            if not os.path.isfile(full_path):
                continue
            with open(full_path, "r", encoding="utf-8") as f:
                raw_text = f.read()
            title, body_md = self._extract_title_and_body(raw_text, match.group("slug"))
            sections.append(
                HelpSection(
                    order=int(match.group("order")),
                    slug=match.group("slug"),
                    title=title,
                    body_md=body_md,
                )
            )
        sections.sort(key=lambda item: (item.order, item.slug))
        return tuple(sections)

    def _extract_title_and_body(self, raw_text: str, fallback_slug: str) -> tuple[str, str]:
        lines = raw_text.splitlines()
        title_index = None
        title = ""
        for idx, line in enumerate(lines):
            stripped = line.strip()
            if not stripped:
                continue
            title_index = idx
            title = stripped.lstrip("#").strip()
            break
        if not title:
            title = fallback_slug.replace("_", " ").replace("-", " ").strip().title()
        body_lines = list(lines)
        if title_index is not None:
            body_lines.pop(title_index)
            while body_lines and not body_lines[0].strip():
                body_lines.pop(0)
        return title, "\n".join(body_lines)

    def _update_nav_width(self) -> None:
        max_text_width = 0
        metrics = QFontMetrics(self.nav_widget.font())
        for i in range(self.nav_widget.count()):
            item = self.nav_widget.item(i)
            max_text_width = max(max_text_width, metrics.horizontalAdvance(item.text()))
        self.nav_widget.setFixedWidth(max(180, max_text_width + 32))

    def _normalize_markdown_lists(self, md_text: str) -> str:
        lines = md_text.splitlines()
        out: list[str] = []
        for line in lines:
            stripped = line.lstrip()
            is_list_item = (
                stripped.startswith("- ")
                or stripped.startswith("* ")
                or stripped.startswith("+ ")
                or (
                    len(stripped) > 2
                    and stripped[0].isdigit()
                    and stripped[1:3] == ". "
                )
            )
            prev_is_list = False
            if out:
                prev_stripped = out[-1].lstrip()
                prev_is_list = (
                    prev_stripped.startswith("- ")
                    or prev_stripped.startswith("* ")
                    or prev_stripped.startswith("+ ")
                    or (
                        len(prev_stripped) > 2
                        and prev_stripped[0].isdigit()
                        and prev_stripped[1:3] == ". "
                    )
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
            return i > 0 and i + 1 < len(s) and s[i] == "." and s[i + 1] == " "

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
                is_ordered = i > 0 and i + 1 < len(s) and s[i] == "." and s[i + 1] == " "
                desired_tag = "ol" if is_ordered else "ul"
                if not in_list or list_tag != desired_tag:
                    if in_list:
                        html_parts.append(f"</{list_tag}>")
                    list_tag = desired_tag
                    in_list = True
                    html_parts.append(f"<{list_tag}>")
                content = s[2:] if list_tag == "ul" else s[i + 2 :]
                html_parts.append(f"<li>{content}</li>")
            else:
                if in_list:
                    html_parts.append(f"</{list_tag}>")
                    in_list = False
                html_parts.append(f"<p>{line}</p>" if line.strip() else "")
        if in_list:
            html_parts.append(f"</{list_tag}>")
        return "\n".join(html_parts)

    def _render_section_html(self, section: HelpSection) -> str:
        md_text = self._normalize_markdown_lists(section.body_md)
        html_content = markdown(
            md_text,
            extensions=["extra", "sane_lists", "smarty", "nl2br"],
        )
        if ("<ul" not in html_content and "<ol" not in html_content) and any(
            l.lstrip().startswith(("- ", "* ", "+ "))
            or (l.lstrip()[:1].isdigit() and ". " in l.lstrip())
            for l in md_text.splitlines()
        ):
            html_content = self._fallback_plainlist_to_html(md_text)
        return html_content

    def change_page(self, index: int) -> None:
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

    def _apply_styles(self) -> None:
        self.theme_manager.apply_theme_to_dialog(self)
        tm = self.theme_manager
        text_color = tm.get_color("dialog.text").name()
        separator_color = tm.get_color("help.separator").name()
        dialog_bg_color = tm.get_color("dialog.background").name()

        def _hex_to_rgb(h: str):
            h = h.lstrip("#")
            if len(h) == 8:
                h = h[2:]
            return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)

        def _rgb_to_hex(r: int, g: int, b: int) -> str:
            return f"#{max(0, min(255, r)):02X}{max(0, min(255, g)):02X}{max(0, min(255, b)):02X}"

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
        code_bg_r, code_bg_g, code_bg_b = _shade(bg_r, bg_g, bg_b, -0.08 if bg_lum > 128 else 0.12)
        code_border_r, code_border_g, code_border_b = _shade(bg_r, bg_g, bg_b, -0.18 if bg_lum > 128 else 0.18)
        code_bg_color = _rgb_to_hex(code_bg_r, code_bg_g, code_bg_b)
        code_border_color = _rgb_to_hex(code_border_r, code_border_g, code_border_b)

        wrapper = f"""
        <style>
            body {{ font-size: 14px; color: {text_color}; }}
            h2 {{ margin-bottom: 8px; border-bottom: 1px solid {separator_color}; padding-bottom: 4px; }}
            h3 {{ margin: 12px 0 6px 0; }}
            ul, ol {{ margin: 8px 0; padding-left: 24px; }}
            li {{ margin: 0 0 6px 0; display: list-item; }}
            b, strong {{ color: {text_color}; }}
            code {{
                background-color: {code_bg_color};
                color: {text_color};
                padding: 2px 4px;
                border-radius: 4px;
                border: 1px solid {code_border_color};
            }}
            pre {{
                background-color: {code_bg_color};
                color: {text_color};
                padding: 10px 12px;
                border-radius: 6px;
                white-space: pre-wrap;
                border: 1px solid {code_border_color};
            }}
            pre code {{
                background-color: transparent;
                color: {text_color};
                padding: 0;
                border: none;
            }}
            kbd {{
                background-color: {code_bg_color};
                color: {text_color};
                padding: 2px 6px;
                border-radius: 4px;
                border: 1px solid {code_border_color};
                font-family: inherit;
            }}
        </style>
        """

        for page, section in zip(self._pages, self._sections):
            page.setText(wrapper + self._render_section_html(section))

    def update_language(self, new_language: str) -> None:
        self.current_language = new_language
        self.setWindowTitle(tr("help.help", language=self.current_language))
        self._reload_sections()
