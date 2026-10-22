"""AI settings page: provider switcher, discovered model list, Apply offer hook.

RED BEFORE: the pre-change page had a single free ``base_url`` field and a free
model text field, no ``settings_ai.MODELS_FOR`` / ``START_TASK`` seam and no
``gallery_ai_provider`` / ``gallery_ai_model_list`` widgets — every test here
raises ``AttributeError`` on the parent commit.

Offscreen only, and hermetic: the discovery seam is injected (no network), the
worker seam runs inline (no thread), and both QSettings groups are redirected so
the real AI config is never read or written.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QSettings

from tabs.image_gallery.services import ai_models
from tabs.image_gallery.services import ai_settings_store as store_module


@pytest.fixture
def gallery_ai_store(monkeypatch):
    """Throwaway AI-settings + model-cache groups for the whole page."""
    monkeypatch.setattr(store_module, "_QS_GROUP", "image_gallery_ai_test_page")
    monkeypatch.setattr(ai_models, "_QS_GROUP", "image_gallery_ai_models_test_page")
    settings = QSettings(store_module._QS_ORG, store_module._QS_APP)
    for group in ("image_gallery_ai_test_page", "image_gallery_ai_models_test_page"):
        settings.remove(group)
    yield
    for group in ("image_gallery_ai_test_page", "image_gallery_ai_models_test_page"):
        settings.remove(group)


@pytest.fixture
def dialog(qapp, gallery_ai_store, monkeypatch):
    """A real SettingsDialog with only the Image Gallery AI page wired."""
    widget = _build_dialog(monkeypatch)
    try:
        yield widget
    finally:
        widget.close()
        widget.deleteLater()


def _build_dialog(monkeypatch, *, owner=None):
    from plugins.settings.registry import (
        ensure_tab_settings_contributions,
        get_settings_registry,
    )
    from plugins.settings.dialog import SettingsDialog
    from tabs.registry import TabRegistry
    from tabs.image_gallery.ui import settings_ai

    registry = TabRegistry()
    registry.discover()
    registry.contribute_all_settings()
    ensure_tab_settings_contributions()
    assert "image_gallery.ai" in {
        section.section_id for section in get_settings_registry().all_sections()
    }

    calls: list[dict] = []

    def _fake_models_for(provider, api_key, *, refresh=False, report=None):
        calls.append(
            {
                "provider": getattr(provider, "id", provider),
                "api_key": api_key,
                "refresh": refresh,
            }
        )
        if report is not None:
            report["reason"] = ai_models.REASON_OK
        return ("fake/model-one", "fake/model-two"), ai_models.SOURCE_NETWORK

    monkeypatch.setattr(settings_ai, "MODELS_FOR", _fake_models_for)
    monkeypatch.setattr(
        settings_ai, "START_TASK", lambda task, on_done: on_done(task())
    )
    # No live gallery tab by default: the Apply offer is asserted separately.
    monkeypatch.setattr(settings_ai, "GALLERY_OWNER", lambda: owner)

    widget = SettingsDialog(
        current_language="en",
        current_theme="dark",
        current_max_length=30,
        min_limit=1,
        max_limit=9999,
        debug_mode_enabled=False,
        system_notifications_enabled=True,
        active_tab="image_gallery",
    )
    widget._ai_calls = calls
    return widget


def _provider_index(dialog, provider_id: str) -> int:
    index = dialog.gallery_ai_provider.findData(provider_id)
    assert index >= 0, f"{provider_id!r} is missing from the provider picker"
    return int(index)


def test_provider_picker_lists_presets_and_started_on_openrouter(dialog):
    from tabs.image_gallery.services.ai_providers import PROVIDER_IDS

    picker = dialog.gallery_ai_provider
    listed = [picker.itemText(i) for i in range(picker.count())]
    assert len(listed) == len(PROVIDER_IDS)
    assert picker.currentData() == "openrouter"
    # A preset owns its endpoint: base_url is not editable.
    assert dialog.gallery_ai_base_url.text() == "https://openrouter.ai/api/v1"
    assert dialog.gallery_ai_base_url.isReadOnly() is True


def test_model_list_is_populated_from_the_injected_discovery(dialog):
    combo = dialog.gallery_ai_model_list
    assert [combo.itemText(i) for i in range(combo.count())] == [
        "fake/model-one",
        "fake/model-two",
    ]
    assert dialog._ai_calls and dialog._ai_calls[0]["provider"] == "openrouter"


def test_provider_change_moves_base_url_and_model(dialog):
    dialog.gallery_ai_provider.setCurrentIndex(_provider_index(dialog, "openai"))

    assert dialog.gallery_ai_base_url.text() == "https://api.openai.com/v1"
    assert dialog.gallery_ai_base_url.isReadOnly() is True
    assert dialog.gallery_ai_model.text() == "gpt-6-luna"
    assert dialog._ai_calls[-1]["provider"] == "openai"


def test_custom_provider_makes_the_url_editable(dialog):
    dialog.gallery_ai_model.setText("vendor/my-vision")
    dialog.gallery_ai_provider.setCurrentIndex(_provider_index(dialog, "custom"))

    assert dialog.gallery_ai_base_url.isReadOnly() is False
    # Switching to the free-form provider keeps the URL the user had.
    assert dialog.gallery_ai_base_url.text() == "https://openrouter.ai/api/v1"


def test_switching_back_restores_the_remembered_model(dialog):
    dialog.gallery_ai_model.setText("vendor/my-vision")
    dialog.gallery_ai_provider.setCurrentIndex(_provider_index(dialog, "openai"))
    assert dialog.gallery_ai_model.text() == "gpt-6-luna"

    dialog.gallery_ai_provider.setCurrentIndex(_provider_index(dialog, "openrouter"))

    assert dialog.gallery_ai_model.text() == "vendor/my-vision"
    assert dialog.gallery_ai_base_url.text() == "https://openrouter.ai/api/v1"


def test_refresh_uses_the_injected_fetch_with_refresh_flag(dialog):
    before = len(dialog._ai_calls)

    dialog.gallery_ai_reload_models()

    assert len(dialog._ai_calls) == before + 1
    assert dialog._ai_calls[-1]["refresh"] is True


def test_an_empty_failed_fetch_reports_on_the_dropdown_itself(dialog, monkeypatch):
    """Owner request 2026-10-22: no caption line — the list row says the reason."""
    from tabs.image_gallery.ui import settings_ai

    def _failing(provider, api_key, *, refresh=False, report=None):
        if report is not None:
            report["reason"] = ai_models.REASON_NETWORK
        return (), ai_models.SOURCE_CURATED

    monkeypatch.setattr(settings_ai, "MODELS_FOR", _failing)
    dialog.gallery_ai_model.setText("vendor/typed-by-hand")

    dialog.gallery_ai_reload_models()

    combo = dialog.gallery_ai_model_list
    assert combo.count() == 1
    assert "no connection" in combo.itemText(0).lower()
    # The error row is not a model: picking it must not rewrite the field.
    assert combo.itemData(0) is None
    combo.setCurrentIndex(0)
    assert dialog.gallery_ai_model.text() == "vendor/typed-by-hand"


def test_no_manual_refresh_control_and_no_status_caption(dialog):
    assert not hasattr(dialog, "gallery_ai_refresh")
    assert not hasattr(dialog, "gallery_ai_models_status")


def test_entering_the_page_re_asks_the_provider(dialog):
    before = len(dialog._ai_calls)

    dialog.section_shown.emit("image_gallery.ai")

    assert len(dialog._ai_calls) == before + 1
    assert dialog._ai_calls[-1]["refresh"] is True
    # Another page's entry must not touch the model list.
    before = len(dialog._ai_calls)
    dialog.section_shown.emit("builtin.general")
    assert len(dialog._ai_calls) == before


def test_identical_catalog_keeps_the_combo_untouched(dialog):
    combo = dialog.gallery_ai_model_list
    combo.setCurrentIndex(combo.findText("fake/model-two"))
    assert combo.currentIndex() == 1

    dialog.gallery_ai_reload_models()  # same fake catalog

    # No rebuild: a rebuild would re-select the persisted field value (index 0).
    assert [combo.itemText(i) for i in range(combo.count())] == [
        "fake/model-one",
        "fake/model-two",
    ]
    assert combo.currentIndex() == 1


def test_changed_catalog_replaces_the_list(dialog, monkeypatch):
    _install_models(monkeypatch, ("vendor/new-one", "vendor/new-two"))

    dialog.gallery_ai_reload_models()

    assert _listed(dialog.gallery_ai_model_list) == [
        "vendor/new-one",
        "vendor/new-two",
    ]


# -- Picker order: publisher first, then model (flat list, no headers) --------

#: The owner's example, in provider order.
SCRAMBLED_MODELS = (
    "meta/muse",
    "deepseek/r1",
    "meta/llama2",
    "deepseek/deepseek-v3",
)


def _install_models(monkeypatch, models):
    """Replace the discovery seam after the dialog is built."""
    from tabs.image_gallery.ui import settings_ai

    def _fake(provider, api_key, *, refresh=False, report=None):
        if report is not None:
            report["reason"] = ai_models.REASON_OK
        return tuple(models), ai_models.SOURCE_NETWORK

    monkeypatch.setattr(settings_ai, "MODELS_FOR", _fake)


def _listed(combo) -> list[str]:
    return [combo.itemText(i) for i in range(combo.count())]


def test_model_list_renders_publisher_first_order(dialog, monkeypatch):
    _install_models(monkeypatch, SCRAMBLED_MODELS)

    dialog.gallery_ai_reload_models()

    assert _listed(dialog.gallery_ai_model_list) == [
        "deepseek/deepseek-v3",
        "deepseek/r1",
        "meta/llama2",
        "meta/muse",
    ]


def test_model_list_restores_the_persisted_selection_after_sorting(dialog, monkeypatch):
    _install_models(monkeypatch, SCRAMBLED_MODELS)
    dialog.gallery_ai_model.setText("meta/muse")

    dialog.gallery_ai_reload_models()

    combo = dialog.gallery_ai_model_list
    assert combo.currentText() == "meta/muse"
    assert combo.currentData() == "meta/muse"
    # Restoring the selection must not rewrite the editable field.
    assert dialog.gallery_ai_model.text() == "meta/muse"


def test_a_typed_custom_model_id_survives_a_refresh(dialog, monkeypatch):
    _install_models(monkeypatch, SCRAMBLED_MODELS)
    dialog.gallery_ai_model.setText("vendor/typed-by-hand")

    dialog.gallery_ai_reload_models()

    # The id is not in the discovered list — the free text field keeps it.
    assert dialog.gallery_ai_model.text() == "vendor/typed-by-hand"


def test_model_tooltips_carry_the_full_id(dialog, monkeypatch):
    _install_models(monkeypatch, SCRAMBLED_MODELS)
    dialog.gallery_ai_reload_models()

    combo = dialog.gallery_ai_model_list
    # Pick from the list: field and closed combo both hover-hint the full id.
    combo.setCurrentIndex(combo.findText("meta/muse"))

    assert dialog.gallery_ai_model.text() == "meta/muse"
    assert dialog.gallery_ai_model.toolTip() == "meta/muse"
    assert combo.toolTip() == "meta/muse"


def test_model_tooltip_follows_a_typed_custom_id(dialog, monkeypatch):
    _install_models(monkeypatch, SCRAMBLED_MODELS)
    dialog.gallery_ai_reload_models()

    dialog.gallery_ai_model.setText("vendor/typed-by-hand")

    assert dialog.gallery_ai_model.toolTip() == "vendor/typed-by-hand"


def test_model_tooltip_is_restored_with_the_persisted_selection(dialog, monkeypatch):
    _install_models(monkeypatch, SCRAMBLED_MODELS)
    dialog.gallery_ai_model.setText("meta/muse")

    dialog.gallery_ai_reload_models()

    assert dialog.gallery_ai_model.toolTip() == "meta/muse"
    assert dialog.gallery_ai_model_list.toolTip() == "meta/muse"


def test_recorded_value_round_trips_through_the_payload_reader(dialog):
    from plugins.settings.registry import get_settings_registry

    dialog.gallery_ai_provider.setCurrentIndex(_provider_index(dialog, "llamacpp"))
    payload = get_settings_registry().read_payloads(dialog)["image_gallery.ai"]

    assert payload["provider_id"] == "llamacpp"
    assert payload["base_url"] == "http://127.0.0.1:8080/v1"


# -- Apply: the re-analyze offer hook -----------------------------------------


class _OfferOwner:
    """Minimal gallery owner for the real Apply -> offer path."""

    def __init__(self, items) -> None:
        from types import SimpleNamespace

        self.state = SimpleNamespace(
            items=list(items),
            selected_paths=set(),
            selected_order=[],
            mode="camera",
        )
        self.widget = SimpleNamespace(visible_paths=lambda: [i.path for i in items])
        self._judgment_domain = "ai"
        self._ai_settings_store = SimpleNamespace(
            load=lambda: SimpleNamespace(reasoning_effort="auto")
        )
        self.ran: list[tuple] = []

    def _tr(self, key: str, default: str) -> str:
        return default

    def reanalyze(self, ctx) -> None:
        self.ran.append(tuple(ctx.targets))


def test_apply_offers_reanalysis_only_after_a_real_identity_change(
    qapp, gallery_ai_store, monkeypatch
):
    """Apply must not ask when nothing changed, and must ask (once) when it did."""
    from types import SimpleNamespace

    from tabs.image_gallery.use_cases import ai_analysis
    from tabs.image_gallery.ui import settings_ai

    item = SimpleNamespace(path=Path("/img/a.png"), analysis={"score": 1}, mtime_ns=0)
    owner = _OfferOwner([item])
    identity = {"model": "vendor/model-a", "base_url": "https://x/v1"}
    asked: list[object] = []

    monkeypatch.setattr(settings_ai, "GALLERY_OWNER", lambda: owner)
    monkeypatch.setattr(settings_ai, "_identity_snapshot", lambda _owner: dict(identity))
    monkeypatch.setattr(
        ai_analysis,
        "_ask_reanalyze_scope",
        lambda ow, parent=None: asked.append(ow) or "all",
    )

    dialog = _build_dialog(monkeypatch, owner=owner)
    try:
        # Unchanged identity -> the modal is never built.
        dialog.confirm_settings()
        assert asked == []
        assert owner.ran == []

        # The provider switch moved the model -> one offer, one re-analysis of
        # the analyzed item via the standard action context.
        identity["model"] = "gpt-6-luna"
        dialog.confirm_settings()
        assert asked == [owner]
        assert owner.ran == [(item.path,)]

        # A second Apply with nothing new does not ask again.
        dialog.confirm_settings()
        assert asked == [owner]
    finally:
        dialog.close()
        dialog.deleteLater()


def test_apply_without_a_live_gallery_tab_does_not_offer(
    qapp, gallery_ai_store, monkeypatch
):
    from tabs.image_gallery.ui import settings_ai

    offers: list[dict] = []
    monkeypatch.setattr(settings_ai, "GALLERY_OWNER", lambda: None)
    monkeypatch.setattr(
        settings_ai,
        "OFFER_REANALYSIS",
        lambda *a, **k: offers.append(k),
    )

    dialog = _build_dialog(monkeypatch, owner=None)
    try:
        dialog.confirm_settings()
        assert offers == []
    finally:
        dialog.close()
        dialog.deleteLater()


# -- i18n: the new labels are real translations in every locale ---------------

_LOCALIZED_KEYS = (
    "image_gallery.settings.provider",
    "image_gallery.settings.models_unavailable",
    "image_gallery.settings.models_reason_auth",
    "image_gallery.settings.models_reason_network",
    "image_gallery.settings.models_reason_http",
    "image_gallery.settings.models_reason_parse",
    "image_gallery.settings.models_reason_no_base_url",
    "image_gallery.settings.reanalyze_title",
    "image_gallery.settings.reanalyze_body",
    "image_gallery.settings.reanalyze_visible",
    "image_gallery.settings.reanalyze_selection",
    "image_gallery.settings.reanalyze_all",
    "image_gallery.settings.reanalyze_not_now",
)


@pytest.mark.parametrize("language", ("ru", "zh", "pt_BR"))
def test_provider_and_offer_keys_are_really_translated(language: str):
    from pathlib import Path

    from resources.translations import add_i18n_root, tr

    root = Path(__file__).resolve().parents[1] / "resources" / "i18n"
    add_i18n_root(root)

    problems: list[str] = []
    for key in _LOCALIZED_KEYS:
        en_value = tr(key, language="en")
        assert en_value and en_value != key, f"{key}: missing from the en reference"
        value = tr(key, language=language)
        if not value or value == key:
            problems.append(f"{key} [{language}]: unresolved -> {value!r}")
        elif value == en_value:
            problems.append(f"{key} [{language}]: English fallback -> {value!r}")
    assert not problems, "\n".join(problems)
