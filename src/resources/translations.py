import json
import os
import logging
from utils.resource_loader import resource_path

logger = logging.getLogger("ImproveImgSLI")

class TranslationManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._translations = {}
            cls._instance._current_lang = "en"
        return cls._instance

    def load_language(self, lang_code):
        if lang_code == self._current_lang and self._translations:
            return

        base_path = resource_path("resources/i18n")
        file_path = os.path.join(base_path, f"{lang_code}.json")

        if not os.path.exists(file_path):
            logger.warning(f"Translation file not found: {file_path}. Falling back to EN.")
            file_path = os.path.join(base_path, "en.json")

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                self._translations = json.load(f)
                self._current_lang = lang_code
        except Exception as e:
            logger.error(f"Failed to load translations: {e}")
            self._translations = {}

    def get(self, text, *args, **kwargs):
        translated = self._translations.get(text, text)

        if args or kwargs:
            try:
                return translated.format(*args, **kwargs)
            except Exception:
                return translated
        return translated

_manager = TranslationManager()

def tr(text, language="en", *args, **kwargs):

    _manager.load_language(language)
    return _manager.get(text, *args, **kwargs)
