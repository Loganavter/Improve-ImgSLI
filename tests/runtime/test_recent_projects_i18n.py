"""Recent panel relative-time and session-type localization."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from tabs.session_picker.recent.cards import format_session_types, localize_session_type
from tabs.session_picker.recent.relative_time import format_relative_opened


def _tr(key: str, default: str = "", *args, **kwargs) -> str:
    ru = {
        "recent.relative.just_now": "только что",
        "recent.relative.minutes": "{n} мин назад",
        "recent.relative.hours": "{n} ч назад",
        "recent.relative.days": "{n} дн назад",
        "types.image_compare": "Сравнение изображений",
        "types.multi_compare": "Мультисравнение",
    }
    return ru.get(key, default or key)


def test_format_relative_opened_uses_tr():
    now = datetime.now(timezone.utc)
    assert format_relative_opened(now.isoformat(), _tr) == "только что"
    minutes_ago = (now - timedelta(minutes=7)).isoformat()
    assert format_relative_opened(minutes_ago, _tr) == "7 мин назад"
    hours_ago = (now - timedelta(hours=3)).isoformat()
    assert format_relative_opened(hours_ago, _tr) == "3 ч назад"


def test_session_types_are_localized():
    assert localize_session_type("image_compare", _tr) == "Сравнение изображений"
    assert (
        format_session_types(("image_compare", "multi_compare"), _tr)
        == "Сравнение изображений, Мультисравнение"
    )
