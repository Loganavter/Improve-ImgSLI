import json
import logging
from typing import Dict

from PyQt6.QtGui import QColor
from utils.resource_loader import resource_path

logger = logging.getLogger("ImproveImgSLI")

def load_themes() -> tuple[Dict[str, QColor], Dict[str, QColor]]:
    themes_path = resource_path("resources/themes.json")
    try:
        with open(themes_path, 'r', encoding='utf-8') as f:
            themes_data = json.load(f)

        light_palette = {k: QColor(v) for k, v in themes_data.get("light", {}).items()}
        dark_palette = {k: QColor(v) for k, v in themes_data.get("dark", {}).items()}

        return light_palette, dark_palette
    except Exception as e:
        logger.error(f"Failed to load themes from {themes_path}: {e}")

        return {}, {}

LIGHT_THEME_PALETTE, DARK_THEME_PALETTE = load_themes()
