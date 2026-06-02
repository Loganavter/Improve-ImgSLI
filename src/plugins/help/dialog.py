from __future__ import annotations

import logging

from resources.translations import tr
from sli_ui_toolkit.ui.widgets.composite.help_sections import (
    normalize_help_language,
    read_markdown_help_sections,
    toc_title_for_language,
)
from sli_ui_toolkit.widgets import MarkdownHelpDialog, MarkdownHelpSection
from ui.icon_manager import AppIcon, get_app_icon
from utils.resource_loader import resource_path

logger = logging.getLogger("ImproveImgSLI")

class HelpDialog(MarkdownHelpDialog):
    def __init__(self, current_language: str, app_name: str, parent=None):
        self.current_language = current_language
        self.app_name = app_name
        self._sections_cache: dict[str, tuple[MarkdownHelpSection, ...]] = {}
        super().__init__(
            title=tr("help.help", language=current_language),
            toc_title=toc_title_for_language(current_language),
            parent=parent,
        )
        self.setWindowIcon(get_app_icon(AppIcon.HELP))
        self.setObjectName("HelpDialog")
        self._apply_styles()
        self._reload_sections()

    def _reload_sections(self) -> None:
        sections = self._discover_sections(self.current_language)
        self.set_sections(sections)
        self.set_toc_title(toc_title_for_language(self.current_language))

    def _discover_sections(self, language: str) -> tuple[MarkdownHelpSection, ...]:
        lang_code = normalize_help_language(language)
        cached = self._sections_cache.get(lang_code)
        if cached is not None:
            return cached

        lang_dir = self._resolve_help_dir(lang_code)
        sections = read_markdown_help_sections(lang_dir)

        if not sections and lang_dir != self._resolve_help_dir("en"):
            sections = read_markdown_help_sections(self._resolve_help_dir("en"))

        self._sections_cache[lang_code] = sections
        return sections

    def _resolve_help_dir(self, language: str) -> str:
        return resource_path(f"resources/help/{normalize_help_language(language)}")

    def update_language(self, new_language: str) -> None:
        self.current_language = new_language
        self.setWindowTitle(tr("help.help", language=self.current_language))
        self._reload_sections()
