from __future__ import annotations

import logging
import os
import re

from PyQt6.QtGui import QIcon

from resources.translations import tr
from sli_ui_toolkit.ui.widgets.composite.markdown_help_dialog import (
    strip_heading_attr_suffix,
)
from sli_ui_toolkit.widgets import MarkdownHelpDialog, MarkdownHelpSection
from ui.icon_manager import AppIcon, get_app_icon
from utils.resource_loader import resource_path

logger = logging.getLogger("ImproveImgSLI")

class HelpDialog(MarkdownHelpDialog):
    _SECTION_PATTERN = re.compile(r"^(?P<order>\d{3})_(?P<slug>.+)\.md$")

    def __init__(self, current_language: str, app_name: str, parent=None):
        self.current_language = current_language
        self.app_name = app_name
        self._sections_cache: dict[str, tuple[MarkdownHelpSection, ...]] = {}
        super().__init__(
            title=tr("help.help", language=current_language),
            toc_title=self._toc_title_for_language(current_language),
            parent=parent,
        )
        self.setWindowIcon(QIcon(get_app_icon(AppIcon.HELP)))
        self.setObjectName("HelpDialog")
        self._apply_styles()
        self._reload_sections()

    def _toc_title_for_language(self, language: str) -> str:
        lang = (language or "en").lower()
        if lang.startswith("ru"):
            return "На этой странице"
        if lang.startswith("pt"):
            return "Nesta pagina"
        if lang.startswith("zh"):
            return "本页内容"
        return "On this page"

    def _reload_sections(self) -> None:
        sections = self._discover_sections(self.current_language)
        self.set_sections(sections)
        self.set_toc_title(self._toc_title_for_language(self.current_language))

    def _discover_sections(self, language: str) -> tuple[MarkdownHelpSection, ...]:
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

    def _read_sections_from_dir(self, directory: str) -> tuple[MarkdownHelpSection, ...]:
        if not os.path.isdir(directory):
            return ()

        sections: list[MarkdownHelpSection] = []
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
                MarkdownHelpSection(
                    order=int(match.group("order")),
                    slug=match.group("slug"),
                    title=title,
                    body_md=body_md,
                )
            )
        return tuple(sorted(sections, key=lambda item: (item.order, item.slug)))

    def _extract_title_and_body(self, raw_text: str, fallback_slug: str) -> tuple[str, str]:
        lines = raw_text.splitlines()
        title_index = None
        title = ""
        for idx, line in enumerate(lines):
            stripped = line.strip()
            if not stripped:
                continue
            title_index = idx
            title = strip_heading_attr_suffix(stripped.lstrip("#").strip())
            break
        if not title:
            title = fallback_slug.replace("_", " ").replace("-", " ").strip().title()
        body_lines = list(lines)
        if title_index is not None:
            body_lines.pop(title_index)
            while body_lines and not body_lines[0].strip():
                body_lines.pop(0)
        return title, "\n".join(body_lines)

    def update_language(self, new_language: str) -> None:
        self.current_language = new_language
        self.setWindowTitle(tr("help.help", language=self.current_language))
        self._reload_sections()
