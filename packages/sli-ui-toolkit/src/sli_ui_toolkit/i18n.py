from __future__ import annotations

import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QObject, pyqtSignal

logger = logging.getLogger(__name__)

class ToolkitTranslationEvents(QObject):
    language_changed = pyqtSignal(str)

def _deep_merge(
    base: dict[str, Any],
    incoming: dict[str, Any],
    source: str,
    *,
    warn_on_override: bool,
) -> None:
    for key, value in incoming.items():
        if key not in base:
            base[key] = value
            continue

        if isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value, source, warn_on_override=warn_on_override)
            continue

        if warn_on_override:
            logger.warning("Translation key override for '%s' from %s", key, source)
        base[key] = value

def _resolve_dotted_key(data: dict[str, Any], dotted_key: str) -> str:
    current: Any = data
    for part in dotted_key.split("."):
        if not isinstance(current, dict) or part not in current:
            return dotted_key
        current = current[part]

    return current if isinstance(current, str) else dotted_key

class TranslationManager:
    _instance: TranslationManager | None = None

    def __new__(cls) -> TranslationManager:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._translations: dict[str, Any] = {}
            cls._instance._cache: dict[str, dict[str, Any]] = {}
            cls._instance._current_lang = "en"
            cls._instance._events = ToolkitTranslationEvents()
            cls._instance._i18n_root: Path | None = None
        return cls._instance

    def set_i18n_root(self, path: str | Path) -> None:
        self._i18n_root = Path(path)
        self._cache.clear()
        self._translations = {}

    def _load_tree(self, lang_dir: Path) -> dict[str, Any]:
        translations: dict[str, Any] = {}
        json_files = sorted(lang_dir.rglob("*.json"))

        if not json_files:
            logger.warning("No translation files found in %s", lang_dir)
            return translations

        for file_path in json_files:
            try:
                file_data = json.loads(file_path.read_text(encoding="utf-8"))
            except Exception as exc:
                logger.error("Failed to load translation file %s: %s", file_path, exc)
                continue

            if not isinstance(file_data, dict):
                logger.warning("Skipping non-object translation file: %s", file_path)
                continue

            _deep_merge(
                translations,
                file_data,
                file_path.relative_to(lang_dir).as_posix(),
                warn_on_override=True,
            )

        return translations

    def _build_language_pack(self, lang_code: str) -> dict[str, Any]:
        if self._i18n_root is None:
            logger.error("i18n root not configured — call configure_i18n(i18n_root=...)")
            return {}

        base_path = self._i18n_root
        fallback_dir = base_path / "en"
        requested_dir = base_path / lang_code

        if not fallback_dir.is_dir():
            logger.error("Fallback translation directory not found: %s", fallback_dir)
            return {}

        translations = self._load_tree(fallback_dir)

        if lang_code == "en":
            return translations

        if not requested_dir.is_dir():
            logger.warning(
                "Translation directory not found: %s. Falling back to EN.",
                requested_dir,
            )
            return translations

        _deep_merge(
            translations,
            self._load_tree(requested_dir),
            requested_dir.relative_to(base_path).as_posix(),
            warn_on_override=False,
        )
        return translations

    def load_language(self, lang_code: str) -> None:
        requested_lang = lang_code or "en"

        if requested_lang == self._current_lang and self._translations:
            return

        cached = self._cache.get(requested_lang)
        if cached is not None:
            self._translations = cached
            self._current_lang = requested_lang
            self._events.language_changed.emit(requested_lang)
            return

        translations = self._build_language_pack(requested_lang)
        self._cache[requested_lang] = translations
        self._translations = translations
        self._current_lang = requested_lang
        self._events.language_changed.emit(requested_lang)

    def get(self, text: str, *args: Any, **kwargs: Any) -> str:
        translated = _resolve_dotted_key(self._translations, text)

        if args or kwargs:
            try:
                return translated.format(*args, **kwargs)
            except Exception:
                return translated
        return translated

_manager = TranslationManager()

def configure_i18n(
    *,
    i18n_root: str | Path | None = None,
    translator: Callable[[str, str | None], str] | None = None,
    language_provider: Callable[[], str] | None = None,
    events: ToolkitTranslationEvents | None = None,
) -> None:
    if i18n_root is not None:
        _manager.set_i18n_root(i18n_root)
    if events is not None:
        _manager._events = events

def translation_events() -> ToolkitTranslationEvents:
    return _manager._events

def emit_language_changed(lang_code: str) -> None:
    translation_events().language_changed.emit(str(lang_code or "en"))

def get_current_language(default: str = "en") -> str:
    return getattr(_manager, "_current_lang", default) or default

def tr(key: str, language: str | None = None, default: str | None = None, *args: Any, **kwargs: Any) -> str:
    lang = language or get_current_language()
    _manager.load_language(lang)
    result = _manager.get(key, *args, **kwargs)
    if result == key and default is not None:
        return default
    return result
