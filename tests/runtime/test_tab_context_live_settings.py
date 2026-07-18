"""TabContext must follow live store.settings after language changes."""

from __future__ import annotations

from dataclasses import dataclass, replace
from types import SimpleNamespace

from tabs.contract import TabContext


@dataclass
class _Settings:
    current_language: str = "en"


def test_tab_context_settings_tracks_store_replacement():
    store = SimpleNamespace(settings=_Settings(current_language="en"))
    stale = store.settings
    context = TabContext(store=store, settings=stale)

    store.settings = replace(stale, current_language="ru")

    assert context.settings is store.settings
    assert context.settings.current_language == "ru"
    assert stale.current_language == "en"


def test_tab_context_tr_uses_live_store_language(monkeypatch):
    calls: list[tuple[str, str | None]] = []

    def fake_tr(key: str, language: str | None = None, default=None, *args, **kwargs):
        calls.append((key, language))
        if language == "ru" and key == "title":
            return "Создать рабочую область"
        return default or key

    monkeypatch.setattr("resources.translations.tr", fake_tr)
    monkeypatch.setattr("resources.translations.get_current_language", lambda: "en")

    store = SimpleNamespace(settings=_Settings(current_language="en"))
    context = TabContext(store=store, settings=store.settings)
    store.settings = replace(store.settings, current_language="ru")

    assert context.tr("title", "Create a workspace") == "Создать рабочую область"
    assert calls[-1] == ("title", "ru")
