"""App translation facade — delegates to sli_ui_toolkit.i18n."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from utils.resource_loader import resource_path

from sli_ui_toolkit import i18n as _toolkit_i18n
from sli_ui_toolkit.i18n import (
    TranslationManager,
    ToolkitTranslationEvents,
    configure_i18n,
    emit_language_changed as _emit_language_changed,
    get_current_language,
    translation_events,
)

_manager = _toolkit_i18n._manager

configure_i18n(i18n_root=Path(resource_path("resources/i18n")))
_manager._current_lang = ""

def add_i18n_root(path: str | Path) -> None:
    _manager.add_i18n_root(path)
    # Defensive: older toolkit builds cleared the pack cache but left the
    # live ``_translations`` pack stale. Rebuild when a language is active.
    current = getattr(_manager, "_current_lang", "") or ""
    if current:
        _manager._translations = _manager.ensure_loaded(current)


def emit_language_changed(lang_code: str) -> None:
    lang = str(lang_code or "en")
    if lang != _manager._current_lang or not _manager._translations:
        _manager._translations = _manager.ensure_loaded(lang)
    _manager._current_lang = lang
    _emit_language_changed(lang)


def tr(
    key: str,
    language: str | None = None,
    default: str | None = None,
    *args: Any,
    **kwargs: Any,
) -> str:
    """Lookup that always honors an explicit ``language`` pack.

    Toolkit ``tr`` historically short-circuits to the live buffer when
    ``language == _current_lang``, which breaks if the buffer and current
    language drift (common after tests restore only ``_current_lang``).
    """
    if language is None:
        result = _manager.get(key, *args, **kwargs)
    else:
        pack = _manager.ensure_loaded(language)
        result = _manager.get_from(pack, key, *args, **kwargs)
    if result == key and default is not None:
        return default
    return result


__all__ = [
    "TranslationManager",
    "ToolkitTranslationEvents",
    "configure_i18n",
    "emit_language_changed",
    "get_current_language",
    "tr",
    "translation_events",
    "add_i18n_root",
]
