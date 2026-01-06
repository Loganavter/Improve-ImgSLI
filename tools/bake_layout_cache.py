import sys
import os
import json
import logging
from pathlib import Path

current_file = Path(__file__).resolve()

current_dir = current_file.parent
project_root = None

for parent in [current_dir, current_dir.parent, current_dir.parent.parent, current_dir.parent.parent.parent]:
    test_path = parent / "src" / "src"
    if test_path.exists() and test_path.is_dir():
        project_root = parent
        break

if project_root is None:

    project_root = current_dir.parent

if (project_root / "src" / "src").exists():
    src_path = project_root / "src" / "src"
    i18n_path = project_root / "src" / "src" / "resources" / "i18n"
    font_path = project_root / "src" / "src" / "shared_toolkit" / "resources" / "fonts" / "SourceSans3-Regular.ttf"
    output_path = project_root / "src" / "src" / "resources" / "layout_cache.json"
else:
    src_path = project_root / "src"
    i18n_path = project_root / "src" / "resources" / "i18n"
    font_path = project_root / "src" / "shared_toolkit" / "resources" / "fonts" / "SourceSans3-Regular.ttf"
    output_path = project_root / "src" / "resources" / "layout_cache.json"

sys.path.insert(0, str(src_path))

from PyQt6.QtGui import QFont, QFontMetrics, QFontDatabase
from PyQt6.QtWidgets import QApplication

from resources.layout_definitions import LAYOUT_DEFINITIONS, LAYOUT_CONFIG

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("LayoutBaker")

def main():

    app = QApplication(sys.argv)

    if not font_path.exists():
        logger.error(f"Font file not found at {font_path}")
        return

    font_id = QFontDatabase.addApplicationFont(str(font_path))
    if font_id == -1:
        logger.warning(f"Failed to load custom font from {font_path}, using default system font")
        font = QFont()
    else:
        family = QFontDatabase.applicationFontFamilies(font_id)[0]
        font = QFont(family)

    font.setPointSize(11)

    fm = QFontMetrics(font)

    languages = {}
    for filename in os.listdir(i18n_path):
        if filename.endswith(".json"):
            lang_code = filename.replace(".json", "")
            with open(i18n_path / filename, 'r', encoding='utf-8') as f:
                languages[lang_code] = json.load(f)

    logger.info(f"Loaded languages: {list(languages.keys())}")

    cache = {}

    DEFAULT_PADDING = 50
    DEFAULT_STRATEGY = "max"

    for group_key, translation_keys in LAYOUT_DEFINITIONS.items():

        config = LAYOUT_CONFIG.get(group_key, {})
        strategy = config.get("strategy", DEFAULT_STRATEGY)

        cache[group_key] = {}

        for lang_code, translations in languages.items():

            calculated_width = 0

            if strategy == "max":

                max_text_w = 0
                padding = config.get("padding", DEFAULT_PADDING)

                for key in translation_keys:
                    text = translations.get(key, key)

                    try:
                        text = text.format(hz="144", fps="240", limit="100", path="...")
                    except Exception:
                        pass

                    w = fm.horizontalAdvance(text)
                    if w > max_text_w:
                        max_text_w = w

                calculated_width = max_text_w + padding

            elif strategy == "sum":

                total_text_w = 0
                item_padding = config.get("item_padding", 20)

                for key in translation_keys:
                    text = translations.get(key, key)
                    w = fm.horizontalAdvance(text)
                    total_text_w += (w + item_padding)

                calculated_width = total_text_w + 10

            cache[group_key][lang_code] = int(calculated_width)

        en_val = cache[group_key].get("en", 0)
        logger.info(f"Group '{group_key}' [{strategy}]: EN width = {en_val}px")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(cache, f, indent=2, sort_keys=True)

    logger.info(f"Successfully baked layout cache to {output_path}")

if __name__ == "__main__":
    main()
