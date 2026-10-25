"""``AiSettingsStore`` field round trips.

The key field goes through ``core.secret_store``, which on a desktop answers
from the login keyring by exec'ing ``secret-tool``. This module used to call
``save_field("api_key", …)`` with no isolation, so
``test_save_and_load_round_trip`` wrote an 11-char stub over the owner's real
73-char provider key in the SHARED keyring entry (measured 2026-10-25) and the
suite stayed green. The key test now asks for the sandboxed keyring
(``secret_store_keyring``: a recording fake ``secret-tool`` + throwaway data
dir, from ``tests/helpers/secret_store_isolation.py``) and clears through the
store on the way out, so even a mis-isolated future run leaves no stub behind.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QSettings

from core import secret_store
from tabs.image_gallery.services import ai_settings_store as store_module
from tabs.image_gallery.services.ai_settings_store import AiSettings, AiSettingsStore, DEFAULT_BASE_URL


@pytest.fixture
def isolated_key_store(secret_store_keyring):
    """A disposable keyring for the ``api_key`` round trip, cleared afterwards.

    ``secret_store_keyring`` pins the backend to the sandbox (the host's login
    keyring is never exec'd) and empties the entry at test start. The teardown
    below clears through the same store that wrote the value: if the sandbox
    ever fails to apply, the stub this test writes still does not survive it.
    """
    secret_store.forget_session_cache()
    secret_store.reset_backend_probe()
    try:
        yield
    finally:
        secret_store.clear()
        secret_store.forget_session_cache()
        secret_store.reset_backend_probe()


def test_load_defaults_when_unset(monkeypatch):
    monkeypatch.setattr(store_module, "_QS_GROUP", "image_gallery_ai_test_defaults")
    settings = QSettings(store_module._QS_ORG, store_module._QS_APP)
    settings.remove("image_gallery_ai_test_defaults")

    result = AiSettingsStore().load()

    assert result == AiSettings(enabled=False, base_url=DEFAULT_BASE_URL, api_key="", model="")
    settings.remove("image_gallery_ai_test_defaults")


def test_save_and_load_round_trip(monkeypatch, isolated_key_store):
    monkeypatch.setattr(store_module, "_QS_GROUP", "image_gallery_ai_test_roundtrip")
    settings = QSettings(store_module._QS_ORG, store_module._QS_APP)
    settings.remove("image_gallery_ai_test_roundtrip")

    store = AiSettingsStore()
    store.save_field("enabled", True)
    store.save_field("base_url", "https://example.test/v1")
    store.save_field("api_key", "sk-test-123")
    store.save_field("model", "some/model")

    # Drop the in-memory copy so the key has to come back out of the backend
    # itself — a cache hit would make this pass without a real round trip.
    secret_store.forget_session_cache()
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