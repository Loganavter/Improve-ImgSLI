from __future__ import annotations

from PySide6.QtCore import QSettings

from tabs.image_gallery.services import ai_settings_store as store_module
from tabs.image_gallery.services.ai_settings_store import AiSettings, AiSettingsStore, DEFAULT_BASE_URL


def test_load_defaults_when_unset(monkeypatch):
    monkeypatch.setattr(store_module, "_QS_GROUP", "image_gallery_ai_test_defaults")
    settings = QSettings(store_module._QS_ORG, store_module._QS_APP)
    settings.remove("image_gallery_ai_test_defaults")

    result = AiSettingsStore().load()

    assert result == AiSettings(enabled=False, base_url=DEFAULT_BASE_URL, api_key="", model="")
    settings.remove("image_gallery_ai_test_defaults")


def test_save_and_load_round_trip(monkeypatch):
    monkeypatch.setattr(store_module, "_QS_GROUP", "image_gallery_ai_test_roundtrip")
    settings = QSettings(store_module._QS_ORG, store_module._QS_APP)
    settings.remove("image_gallery_ai_test_roundtrip")

    store = AiSettingsStore()
    store.save_field("enabled", True)
    store.save_field("base_url", "https://example.test/v1")
    store.save_field("api_key", "sk-test-123")
    store.save_field("model", "some/model")

    loaded = store.load()

    # No stored ``provider_id``: a pre-provider config loads as ``custom`` and
    # keeps its own URL verbatim (the user's endpoint is not re-written to a
    # preset they never chose).
    assert loaded == AiSettings(
        enabled=True,
        base_url="https://example.test/v1",
        api_key="sk-test-123",
        model="some/model",
        provider_id="custom",
    )
    settings.remove("image_gallery_ai_test_roundtrip")


def test_save_and_load_ask_budget_and_effort(monkeypatch):
    monkeypatch.setattr(store_module, "_QS_GROUP", "image_gallery_ai_test_ask")
    settings = QSettings(store_module._QS_ORG, store_module._QS_APP)
    settings.remove("image_gallery_ai_test_ask")

    store = AiSettingsStore()
    store.save_field("ask_max_tokens", 2048)
    store.save_field("reasoning_effort", "high")

    loaded = store.load()
    assert loaded.ask_max_tokens == 2048
    assert loaded.reasoning_effort == "high"
    settings.remove("image_gallery_ai_test_ask")


def test_load_sanitizes_invalid_ask_settings(monkeypatch):
    monkeypatch.setattr(store_module, "_QS_GROUP", "image_gallery_ai_test_ask_bad")
    settings = QSettings(store_module._QS_ORG, store_module._QS_APP)
    settings.remove("image_gallery_ai_test_ask_bad")

    store = AiSettingsStore()
    store.save_field("ask_max_tokens", -5)
    store.save_field("reasoning_effort", "bogus")

    loaded = store.load()
    assert loaded.ask_max_tokens == 0
    assert loaded.reasoning_effort == "auto"
    settings.remove("image_gallery_ai_test_ask_bad")


def test_save_and_load_vlm_max_edge(monkeypatch):
    monkeypatch.setattr(store_module, "_QS_GROUP", "image_gallery_ai_test_vlm_edge")
    settings = QSettings(store_module._QS_ORG, store_module._QS_APP)
    settings.remove("image_gallery_ai_test_vlm_edge")

    store = AiSettingsStore()
    store.save_field("vlm_max_edge_px", 768)
    assert store.load().vlm_max_edge_px == 768
    store.save_field("vlm_max_edge_px", 999)
    assert store.load().vlm_max_edge_px == 1024
    store.save_field("vlm_max_edge_px", 0)
    assert store.load().vlm_max_edge_px == 0
    settings.remove("image_gallery_ai_test_vlm_edge")


def test_save_field_rejects_unknown_name():
    store = AiSettingsStore()
    try:
        store.save_field("not_a_real_field", "x")
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for unknown field name")