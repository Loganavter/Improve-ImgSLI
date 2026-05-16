"""App translation facade — delegates to sli_ui_toolkit.i18n."""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QObject

from utils.resource_loader import resource_path

from sli_ui_toolkit.i18n import (
    TranslationManager,
    ToolkitTranslationEvents,
    configure_i18n,
    emit_language_changed,
    get_current_language,
    tr,
    translation_events,
)

configure_i18n(i18n_root=Path(resource_path("resources/i18n")))

__all__ = [
    "TranslationManager",
    "ToolkitTranslationEvents",
    "configure_i18n",
    "emit_language_changed",
    "get_current_language",
    "tr",
    "translation_events",
]
