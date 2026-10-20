"""Provider presets + per-provider model memory (gallery AI settings).

RED BEFORE: the pre-change tree had no ``services/ai_providers`` module at all
(``from ... import ai_providers`` was a ``ModuleNotFoundError``) and
``AiSettingsStore`` had no ``save_provider`` / ``model_for``, so switching the
endpoint silently kept the previous provider's model.

Pins the three owner decisions behind the provider picker:

* a named preset OWNS its default base_url (URL → preset resolution is
  normalized: trailing slash, host case);
* the model remembered for a provider is restored when you switch back, and a
  first visit falls back to the curated default;
* the curated tuples stay honest fallbacks (short, and a default model that is
  actually in the fallback list).
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QSettings

from tabs.image_gallery.services import ai_providers as providers
from tabs.image_gallery.services import ai_settings_store as store_module
from tabs.image_gallery.services.ai_settings_store import AiSettingsStore

OPENROUTER_URL = "https://openrouter.ai/api/v1"
OPENAI_URL = "https://api.openai.com/v1"
LLAMACPP_URL = "http://127.0.0.1:8080/v1"


@pytest.fixture
def isolated_store(monkeypatch):
    """A throwaway QSettings group — the real AI config is never touched."""
    monkeypatch.setattr(store_module, "_QS_GROUP", "image_gallery_ai_test_providers")
    settings = QSettings(store_module._QS_ORG, store_module._QS_APP)
    settings.remove("image_gallery_ai_test_providers")
    yield AiSettingsStore()
    settings.remove("image_gallery_ai_test_providers")


# -- A. provider presets -------------------------------------------------------


def test_provider_for_resolves_each_preset_url():
    assert providers.provider_for(OPENROUTER_URL).id == "openrouter"
    assert providers.provider_for(OPENAI_URL).id == "openai"
    assert providers.provider_for(LLAMACPP_URL).id == "llamacpp"


def test_provider_for_normalizes_trailing_slash_and_host_case():
    assert providers.provider_for("https://openrouter.ai/api/v1/").id == "openrouter"
    assert providers.provider_for("  https://OpenRouter.AI/api/v1  ").id == "openrouter"
    assert providers.provider_for("https://API.OPENAI.COM/v1/").id == "openai"


def test_provider_for_unknown_url_is_custom():
    assert providers.provider_for("https://example.test/v1").id == "custom"
    assert providers.provider_for("").id == "custom"
    assert providers.provider_for(None).id == "custom"


def test_provider_by_id_round_trips_and_unknown_is_custom():
    for provider in providers.PROVIDERS:
        assert providers.provider_by_id(provider.id) is provider
    assert providers.provider_by_id("not-a-provider").id == "custom"
    assert providers.provider_by_id("").id == "custom"


def test_presets_carry_an_honest_curated_fallback():
    """Curated lists are fallbacks: short, and they contain their own default."""
    for provider in providers.PROVIDERS:
        assert len(provider.curated_models) <= 5, provider.id
        if provider.default_model:
            assert provider.default_model in provider.curated_models, provider.id
    # The free-form endpoint owns neither a URL nor a catalog.
    custom = providers.provider_by_id("custom")
    assert custom.base_url == ""
    assert custom.curated_models == ()
    # A local llama.cpp server serves whatever it was started with — a made-up
    # curated name would be a model the server cannot answer for.
    assert providers.provider_by_id("llamacpp").default_model == ""


def test_model_for_prefers_remembered_over_default():
    openai = providers.provider_by_id("openai")
    assert providers.model_for(openai, "") == openai.default_model
    assert providers.model_for(openai, "vendor/custom-vision") == "vendor/custom-vision"


# -- C. per-provider model memory ---------------------------------------------


def test_first_visit_uses_the_curated_default(isolated_store):
    openrouter = providers.provider_by_id("openrouter")

    assert isolated_store.model_for("openrouter") == ""
    assert (
        providers.model_for(openrouter, isolated_store.model_for("openrouter"))
        == openrouter.default_model
    )


def test_switching_away_and_back_restores_the_remembered_model(isolated_store):
    openrouter = providers.provider_by_id("openrouter")

    isolated_store.save_provider("openrouter", OPENROUTER_URL, "vendor/model-a")
    # Switch to OpenAI: nothing remembered there yet -> its curated default.
    assert isolated_store.model_for("openai") == ""
    isolated_store.save_provider("openai", OPENAI_URL, "gpt-6-luna")
    # Switch back: OpenRouter's model returns, not OpenAI's.
    assert isolated_store.model_for("openrouter") == "vendor/model-a"
    assert (
        providers.model_for(openrouter, isolated_store.model_for("openrouter"))
        == "vendor/model-a"
    )

    loaded = isolated_store.load()
    assert loaded.provider_id == "openai"
    assert loaded.model == "gpt-6-luna"
    assert loaded.model_for("openrouter") == "vendor/model-a"
    assert loaded.provider_models == {
        "openrouter": "vendor/model-a",
        "openai": "gpt-6-luna",
    }


def test_save_provider_moves_url_and_model_together(isolated_store):
    isolated_store.save_field("model", "openrouter/auto")
    isolated_store.save_provider("openai", OPENAI_URL, "gpt-6-luna")

    loaded = isolated_store.load()
    assert loaded.provider_id == "openai"
    assert loaded.base_url == OPENAI_URL
    assert loaded.model == "gpt-6-luna"


def test_empty_model_is_not_remembered(isolated_store):
    isolated_store.save_provider("llamacpp", LLAMACPP_URL, "")
    assert isolated_store.model_for("llamacpp") == ""


def test_legacy_config_without_provider_loads_as_custom(isolated_store):
    """A config written before providers existed keeps its own URL, editable."""
    isolated_store.save_field("base_url", "https://my-endpoint.test/v1")
    isolated_store.save_field("model", "my/vision")

    loaded = isolated_store.load()
    assert loaded.provider_id == "custom"
    assert loaded.base_url == "https://my-endpoint.test/v1"
    assert loaded.model == "my/vision"


def test_fresh_config_starts_on_the_default_preset(isolated_store):
    assert isolated_store.load().provider_id == "openrouter"
