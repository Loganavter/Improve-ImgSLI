from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from PyQt6.QtCore import QEvent, QSize, Qt, QUrl
from PyQt6.QtGui import QDesktopServices, QFontMetrics
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QListWidgetItem,
    QScrollArea,
    QSizePolicy,
    QTextBrowser,
)
from markdown import markdown

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.widgets.atomic.minimalist_scrollbar import MinimalistScrollBar
from sli_ui_toolkit.ui.widgets.composite.dialog_shell import SidebarDialogShell

@dataclass(frozen=True)
class MarkdownHelpSection:
    order: int
    slug: str
    title: str
    body_md: str

_TITLE_ATTR_SUFFIX_RE = re.compile(r"\s*\{#[-a-zA-Z0-9_:.]+\}\s*$")
_HEADING_TAG_RE = re.compile(
    r"<h(?P<level>[1-6])(?P<attrs>[^>]*)>(?P<text>.*?)</h(?P=level)>",
    re.IGNORECASE | re.DOTALL,
)
_HEADING_ID_RE = re.compile(r"""\sid\s*=\s*["'][^"']+["']""", re.IGNORECASE)
_H3_WITH_ID_RE = re.compile(
    r'<h3(?P<attrs>[^>]*)\sid="(?P<id>[^"]+)"[^>]*>(?P<text>.*?)</h3>',
    re.IGNORECASE | re.DOTALL,
)

def strip_heading_attr_suffix(text: str) -> str:
    return _TITLE_ATTR_SUFFIX_RE.sub("", text).strip()

def slugify_anchor(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_text).strip("-").lower()
    return slug

def strip_html_tags(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text)

def ensure_heading_ids(html: str, *, fallback_prefix: str) -> str:
    counters: dict[str, int] = {}
    generated_index = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal generated_index
        attrs = match.group("attrs") or ""
        if _HEADING_ID_RE.search(attrs):
            return match.group(0)

        plain_text = strip_html_tags(match.group("text") or "")
        base = slugify_anchor(plain_text)
        if not base:
            base = f"{fallback_prefix}-section-{generated_index}"
            generated_index += 1

        count = counters.get(base, 0)
        counters[base] = count + 1
        anchor_id = base if count == 0 else f"{base}-{count + 1}"
        return f'<h{match.group("level")}{attrs} id="{anchor_id}">{match.group("text")}</h{match.group("level")}>'

    return _HEADING_TAG_RE.sub(replace, html)

def build_page_toc(html: str, *, title: str) -> str:
    items: list[tuple[str, str]] = []
    for match in _H3_WITH_ID_RE.finditer(html):
        anchor_id = match.group("id").strip()
        text = strip_html_tags(match.group("text") or "").strip()
        if anchor_id and text:
            items.append((anchor_id, text))
    if len(items) < 2:
        return ""

    links = "".join(
        f'<li><a href="#{anchor_id}">{text}</a></li>'
        for anchor_id, text in items
    )
    return (
        '<nav class="help-toc">'
        f'<div class="help-toc-title">{title}</div>'
        f"<ul>{links}</ul>"
        "</nav>"
    )

class MarkdownHelpPageBrowser(QTextBrowser):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setOpenLinks(False)
        self.setOpenExternalLinks(False)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setReadOnly(True)
        self.setLineWrapMode(QTextBrowser.LineWrapMode.WidgetWidth)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setStyleSheet("background: transparent; border: none;")
        self.document().setDocumentMargin(25)
        layout = self.document().documentLayout()
        if layout is not None:
            layout.documentSizeChanged.connect(lambda _size: self.updateGeometry())

    def sizeHint(self):
        height = max(200, int(round(self.document().size().height())) + 8)
        return QSize(400, height)

    def minimumSizeHint(self):
        return self.sizeHint()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        viewport_width = max(1, self.viewport().width())
        margin = self.document().documentMargin() * 2
        self.document().setTextWidth(max(1.0, float(viewport_width - margin)))
        self.updateGeometry()

    def anchor_vertical_offset(self, anchor: str) -> int | None:
        anchor = (anchor or "").strip()
        if not anchor:
            return None

        layout = self.document().documentLayout()
        if layout is None:
            return None

        block = self.document().begin()
        while block.isValid():
            it = block.begin()
            while not it.atEnd():
                fragment = it.fragment()
                if fragment.isValid():
                    fmt = fragment.charFormat()
                    if fmt.isAnchor() and anchor in fmt.anchorNames():
                        rect = layout.blockBoundingRect(block)
                        return max(0, int(round(rect.top())))
                it += 1
            block = block.next()
        return None

class MarkdownHelpDialog(QDialog):
    def __init__(
        self,
        *,
        title: str = "Help",
        toc_title: str = "On this page",
        sections: tuple[MarkdownHelpSection, ...] | list[MarkdownHelpSection] = (),
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("MarkdownHelpDialog")
        self.theme_manager = ThemeManager.get_instance()
        self._pages: list[MarkdownHelpPageBrowser] = []
        self._sections: tuple[MarkdownHelpSection, ...] = ()
        self._toc_title_text = str(toc_title)

        self.setWindowTitle(title)
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.setSizeGripEnabled(True)
        self.resize(800, 600)
        self.setMinimumSize(300, 200)

        self._setup_ui()
        self.set_sections(sections)
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
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_area.setVerticalScrollBar(MinimalistScrollBar())
        self.scroll_area.setHorizontalScrollBar(MinimalistScrollBar())
        self.scroll_area.viewport().installEventFilter(self)

        self.shell.pages_stack.hide()
        self.shell.content_layout.addWidget(self.scroll_area, 1)
        main_layout.addWidget(self.shell)

    def set_toc_title(self, title: str) -> None:
        self._toc_title_text = str(title)
        self._apply_styles()

    def set_sections(
        self,
        sections: tuple[MarkdownHelpSection, ...] | list[MarkdownHelpSection],
    ) -> None:
        self._sections = tuple(sorted(sections, key=lambda item: (item.order, item.slug)))
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
            content_page = MarkdownHelpPageBrowser()
            content_page.anchorClicked.connect(self._on_anchor_clicked)
            self._pages.append(content_page)

        if self.nav_widget.count() > 0:
            self.nav_widget.setCurrentRow(0)

        self._update_nav_width()
        self._apply_styles()

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

    def _render_section_html(self, section: MarkdownHelpSection) -> str:
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
        html_content = ensure_heading_ids(html_content, fallback_prefix=section.slug)
        toc_html = build_page_toc(html_content, title=self._toc_title_text)
        return toc_html + html_content

    def change_page(self, index: int) -> None:
        if index < 0 or index >= len(self._pages):
            return

        old_widget = self.scroll_area.takeWidget()
        if old_widget is not None:
            old_widget.hide()
            old_widget.setParent(None)

        page = self._pages[index]
        self.scroll_area.setWidget(page)
        self._sync_page_width(page)
        page.show()
        page.adjustSize()
        self.scroll_area.verticalScrollBar().setValue(0)

    def _sync_page_width(self, page: MarkdownHelpPageBrowser | None) -> None:
        if page is None:
            return
        viewport_width = max(1, self.scroll_area.viewport().width())
        page.setFixedWidth(viewport_width)
        margin = page.document().documentMargin() * 2
        page.document().setTextWidth(max(1.0, float(viewport_width - margin)))
        page.updateGeometry()
        page.adjustSize()

    def eventFilter(self, watched, event):
        if watched is self.scroll_area.viewport() and event.type() == QEvent.Type.Resize:
            current = self.scroll_area.widget()
            if isinstance(current, MarkdownHelpPageBrowser):
                self._sync_page_width(current)
        return super().eventFilter(watched, event)

    def _find_section_index(self, slug: str) -> int:
        for index, section in enumerate(self._sections):
            if section.slug == slug:
                return index
        return -1

    def _navigate_to_help_target(self, slug: str, anchor: str | None = None) -> None:
        index = self._find_section_index(slug)
        if index < 0:
            return
        self.nav_widget.setCurrentRow(index)
        if anchor:
            self._scroll_current_page_to_anchor(anchor)

    def _scroll_current_page_to_anchor(self, anchor: str) -> None:
        current = self.nav_widget.currentRow()
        if not (0 <= current < len(self._pages)):
            return
        page = self._pages[current]
        y = page.anchor_vertical_offset(anchor)
        if y is None:
            return
        self.scroll_area.verticalScrollBar().setValue(y)

    def _on_anchor_clicked(self, url: QUrl) -> None:
        if url.isRelative():
            anchor = url.fragment().strip()
            if anchor:
                self._scroll_current_page_to_anchor(anchor)
            return

        scheme = (url.scheme() or "").lower()
        if scheme in {"http", "https"}:
            QDesktopServices.openUrl(url)
            return

        if scheme == "help":
            slug = url.host().strip() or url.path().strip("/")
            if slug:
                self._navigate_to_help_target(slug, url.fragment().strip() or None)

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
            p {{
                overflow-wrap: anywhere;
                word-break: normal;
            }}
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
            a {{
                color: {tm.get_color("accent").name()};
                text-decoration: none;
            }}
            .help-toc {{
                margin: 0 0 16px 0;
                padding: 10px 14px;
                border: 1px solid {separator_color};
                border-radius: 8px;
            }}
            .help-toc-title {{
                font-weight: 600;
                margin-bottom: 6px;
            }}
            .help-toc ul {{
                margin: 0;
                padding-left: 18px;
            }}
            .help-toc li {{
                margin-bottom: 4px;
            }}
        </style>
        """

        for page, section in zip(self._pages, self._sections):
            page.setHtml(wrapper + self._render_section_html(section))

