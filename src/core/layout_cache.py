import json
import os
import logging
from utils.resource_loader import resource_path

logger = logging.getLogger("ImproveImgSLI")

class LayoutCache:
    _instance = None
    _cache = {}

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self._load_cache()

    def _load_cache(self):

        path = resource_path("resources/layout_cache.json")
        try:
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    self._cache = json.load(f)
            else:

                logger.warning(f"Layout cache file not found at {path}")
        except Exception as e:
            logger.error(f"Failed to load layout cache: {e}")

    def get_fixed_width(self, group_key: str, lang_code: str = "en") -> int | None:
        group_data = self._cache.get(group_key)

        if not group_data:
            return None

        if isinstance(group_data, (int, float)):
            return int(group_data)

        if isinstance(group_data, dict):

            if lang_code in group_data:
                return int(group_data[lang_code])
            elif "en" in group_data:
                return int(group_data["en"])
            elif group_data:
                return int(max(group_data.values()))

        return None

    def get_container_width(self, group_key: str, lang_code: str = "en") -> int:
        val = self.get_fixed_width(group_key, lang_code)

        return val if val is not None else 200
