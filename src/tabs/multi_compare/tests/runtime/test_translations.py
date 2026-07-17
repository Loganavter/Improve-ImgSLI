"""MultiCompare controls use tab-owned translations for every supported language."""

import json
from pathlib import Path

TAB_ROOT = Path(__file__).parents[2]
I18N_ROOT = TAB_ROOT / "resources" / "i18n"


def _translations(language: str) -> dict[str, str]:
    return json.loads(
        (I18N_ROOT / language / "multi_compare.json").read_text(encoding="utf-8")
    )


def test_multi_compare_buttons_have_english_and_russian_translations():
    english = _translations("en")
    russian = _translations("ru")

    assert english["add_images"] == "Add images"
    assert english["save_result"] == "Save result"
    assert russian["add_images"] == "Добавить изображения"
    assert russian["save_result"] == "Сохранить результат"


def test_multi_compare_buttons_are_constructed_with_visible_text():
    toolbar_source = (TAB_ROOT / "ui" / "toolbar.py").read_text(encoding="utf-8")
    footer_source = (TAB_ROOT / "ui" / "footer.py").read_text(encoding="utf-8")

    assert 'Icon.PHOTO, text=text' in toolbar_source
    assert 'Icon.SAVE, text=text' in footer_source
