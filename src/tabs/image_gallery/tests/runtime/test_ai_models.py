"""Model discovery: OpenAI-compatible ``/models`` → cache → curated fallback.

RED BEFORE: the pre-change tree had no ``services/ai_models`` module
(``ModuleNotFoundError``) — the settings page asked the user to type a model
with no way to see what the provider actually serves.

The three layers are pinned here with an injected HTTP function (no real
network, no real key):

* a 200 with ``{"data": [{"id": ...}]}`` is parsed and remembered;
* a 401 is a NAMED failure (``auth``) that falls back to the curated list;
* a fresh cache avoids a second call (the fake records its call count), an
  explicit refresh does call again, and a stale cache survives a dead endpoint.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QSettings

from tabs.image_gallery.services import ai_models
from tabs.image_gallery.services.ai_providers import provider_by_id


@pytest.fixture(autouse=True)
def isolated_cache(monkeypatch):
    """A throwaway QSettings group for the fetched catalog."""
    monkeypatch.setattr(ai_models, "_QS_GROUP", "image_gallery_ai_models_test")
    settings = QSettings(ai_models._QS_ORG, ai_models._QS_APP)
    settings.remove("image_gallery_ai_models_test")
    yield
    settings.remove("image_gallery_ai_models_test")


class _FakeHttp:
    """A counting stand-in for ``GET {base_url}/models``."""

    def __init__(self, models=(), reason=ai_models.REASON_OK, raises=None):
        self.models = tuple(models)
        self.reason = reason
        self.raises = raises
        self.calls: list[tuple[str, str]] = []

    def __call__(self, base_url, api_key, timeout=5):
        self.calls.append((str(base_url), str(api_key)))
        if self.raises is not None:
            raise self.raises
        return self.models, self.reason


OPENROUTER = provider_by_id("openrouter")
NOW = 1_800_000_000.0


def test_parse_models_reads_the_openai_envelope():
    payload = {"data": [{"id": "vendor/a"}, {"id": "vendor/b"}, {"id": "vendor/a"}]}
    assert ai_models.parse_models(payload) == ("vendor/a", "vendor/b")


def test_parse_models_tolerates_shapes_without_ids():
    assert ai_models.parse_models({"data": [{"id": "x"}, {"object": "model"}]}) == ("x",)
    assert ai_models.parse_models(["plain/a", ""]) == ("plain/a",)
    assert ai_models.parse_models({"unexpected": True}) == ()
    assert ai_models.parse_models(None) == ()


def test_fetch_models_parses_http_payload():
    http = _FakeHttp(models=("vendor/vision-1", "vendor/vision-2"))
    models, reason = ai_models.fetch_models(
        OPENROUTER.base_url, "sk-test", http=http
    )
    assert models == ("vendor/vision-1", "vendor/vision-2")
    assert reason == ai_models.REASON_OK
    assert http.calls == [(OPENROUTER.base_url, "sk-test")]


def test_models_for_network_result_is_cached_for_the_provider():
    http = _FakeHttp(models=("vendor/vision-1",))

    models, source = ai_models.models_for(OPENROUTER, "sk", http=http, now=NOW)

    assert (models, source) == (("vendor/vision-1",), ai_models.SOURCE_NETWORK)
    cached, fetched_at = ai_models.cached_models("openrouter")
    assert cached == ("vendor/vision-1",)
    assert fetched_at == NOW


def test_fresh_cache_avoids_a_second_call():
    http = _FakeHttp(models=("vendor/vision-1",))

    first = ai_models.models_for(OPENROUTER, "sk", http=http, now=NOW)
    second = ai_models.models_for(OPENROUTER, "sk", http=http, now=NOW + 60)

    assert first[1] == ai_models.SOURCE_NETWORK
    assert second == (("vendor/vision-1",), ai_models.SOURCE_CACHE)
    assert len(http.calls) == 1


def test_explicit_refresh_calls_again_even_on_a_fresh_cache():
    http = _FakeHttp(models=("vendor/vision-1",))

    ai_models.models_for(OPENROUTER, "sk", http=http, now=NOW)
    models, source = ai_models.models_for(
        OPENROUTER, "sk", http=http, now=NOW + 60, refresh=True
    )

    assert (models, source) == (("vendor/vision-1",), ai_models.SOURCE_NETWORK)
    assert len(http.calls) == 2


def test_stale_cache_is_used_when_the_refresh_fails():
    http = _FakeHttp(models=("vendor/vision-1",))
    ai_models.models_for(OPENROUTER, "sk", http=http, now=NOW)

    dead = _FakeHttp(reason=ai_models.REASON_NETWORK)
    report: dict = {}
    models, source = ai_models.models_for(
        OPENROUTER,
        "sk",
        http=dead,
        now=NOW + ai_models.MODEL_CACHE_TTL_S + 1,
        report=report,
    )

    assert (models, source) == (("vendor/vision-1",), ai_models.SOURCE_CACHE)
    assert report["reason"] == ai_models.REASON_NETWORK


def test_unauthorized_is_a_named_failure_that_falls_back_to_curated():
    http = _FakeHttp(reason=ai_models.REASON_AUTH)
    report: dict = {}

    models, source = ai_models.models_for(
        OPENROUTER, "bad-key", http=http, report=report
    )

    assert source == ai_models.SOURCE_CURATED
    assert models == OPENROUTER.curated_models
    assert report["reason"] == ai_models.REASON_AUTH


def test_missing_base_url_never_calls_the_endpoint():
    custom = provider_by_id("custom")
    http = _FakeHttp(models=("should/not/appear",))
    report: dict = {}

    models, source = ai_models.models_for(custom, "sk", http=http, report=report)

    assert (models, source) == ((), ai_models.SOURCE_CURATED)
    assert report["reason"] == ai_models.REASON_NO_BASE_URL
    assert http.calls == []


def test_a_raising_transport_is_a_named_failure_not_an_exception():
    http = _FakeHttp(raises=OSError("boom"))
    report: dict = {}

    models, source = ai_models.models_for(OPENROUTER, "sk", http=http, report=report)

    assert (models, source) == (OPENROUTER.curated_models, ai_models.SOURCE_CURATED)
    assert report["reason"] == ai_models.REASON_NETWORK


def test_unreadable_body_is_a_parse_failure(monkeypatch):
    monkeypatch.setattr(ai_models, "HTTP_GET", lambda *a, **k: ((), ai_models.REASON_PARSE))

    models, source = ai_models.models_for(OPENROUTER, "sk")

    assert source == ai_models.SOURCE_CURATED
    assert models == OPENROUTER.curated_models


def test_cached_models_ignores_a_corrupt_value(monkeypatch):
    class _FakeSettings:
        def value(self, key, default=None):
            return "{not json"

        def endGroup(self) -> None:
            return None

    monkeypatch.setattr(ai_models, "_settings", lambda: _FakeSettings())

    assert ai_models.cached_models("openrouter") == ((), 0.0)


# -- Picker order: publisher first, then model (flat list, no headers) --------


def test_publisher_of_is_the_part_before_the_first_slash():
    assert ai_models.publisher_of("meta/llama2") == "meta"
    assert ai_models.publisher_of("a/b/c") == "a"
    assert ai_models.publisher_of("gpt-6-luna") == ""
    assert ai_models.publisher_of("") == ""
    assert ai_models.publisher_of(None) == ""


def test_sorted_models_matches_the_owner_example():
    """Provider order in: meta/muse, deepseek/r1, meta/llama2, deepseek/…v3."""
    provider_order = (
        "meta/muse",
        "deepseek/r1",
        "meta/llama2",
        "deepseek/deepseek-v3",
    )

    assert ai_models.sorted_models(provider_order) == (
        "deepseek/deepseek-v3",
        "deepseek/r1",
        "meta/llama2",
        "meta/muse",
    )


def test_sorted_models_compares_publishers_case_insensitively():
    # Plain ASCII sort would put "Meta/Muse" first; casefold puts it under "m".
    assert ai_models.sorted_models(("Meta/Muse", "deepseek/r1")) == (
        "deepseek/r1",
        "Meta/Muse",
    )


def test_sorted_models_dedupes_exact_ids_and_keeps_case_variants():
    assert ai_models.sorted_models(("a/b", "a/b", "a/c")) == ("a/b", "a/c")
    # Case variants are distinct ids a provider can serve; the original string
    # breaks the tie deterministically.
    assert ai_models.sorted_models(("openai/gpt", "OpenAI/GPT")) == (
        "OpenAI/GPT",
        "openai/gpt",
    )


def test_sorted_models_treats_a_bare_id_as_its_own_publisher():
    # "gpt-6-luna" sorts by its own name among the vendor-prefixed ids.
    assert ai_models.sorted_models(("zeta/model", "gpt-6-luna", "alpha/model")) == (
        "alpha/model",
        "gpt-6-luna",
        "zeta/model",
    )


def test_sorted_models_keeps_the_rest_of_a_multi_slash_id_together():
    assert ai_models.sorted_models(("a/z/x", "a/b/y", "a/b/c")) == (
        "a/b/c",
        "a/b/y",
        "a/z/x",
    )


def test_sorted_models_never_raises_on_junk():
    assert ai_models.sorted_models(None) == ()
    assert ai_models.sorted_models(["", "  ", 5]) == ("5",)
