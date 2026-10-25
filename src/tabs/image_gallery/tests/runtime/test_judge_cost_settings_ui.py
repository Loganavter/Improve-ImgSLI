"""AI settings page: the two judge cost settings are real, saved choices.

``AiSettings.judge_concurrency`` (default 3, clamped 1..8) and
``AiSettings.judge_run_call_ceiling`` (0 = unlimited) were persisted, clamped
and honoured by ``use_cases/scheduler`` / ``use_cases/judge_budget``, but
``ui/settings_ai.py`` had no row for either — a user could only change them by
editing QSettings by hand.

RED BEFORE: the pre-change page has no ``gallery_ai_judge_concurrency`` /
``gallery_ai_judge_ceiling`` widget and neither key is in the settings payload,
so every test here fails on the parent commit with ``AttributeError`` /
``KeyError``.

What is pinned: the write goes through ``AiSettingsStore.save_field`` (the one
owner of both clamps), the control re-reads the STORE after a write instead of
echoing the widget's input, 0 renders as the localized "unlimited" word, and
all four locale bundles + help pages carry the wording.

Offscreen only and hermetic: the AI-settings + model-cache QSettings groups are
redirected to throwaway groups, and the page's network/worker/owner seams come
from the sibling settings-page fixture builder (no network, no app, no dialog).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings

from tabs.image_gallery.services import ai_models
from tabs.image_gallery.services import ai_settings_store as store_module
from tabs.image_gallery.services.ai_settings_store import (
    JUDGE_CONCURRENCY_DEFAULT,
    JUDGE_CONCURRENCY_MAX,
    AiSettingsStore,
)

_I18N_ROOT = Path(__file__).resolve().parents[2] / "resources" / "i18n"
_HELP_ROOT = Path(__file__).resolve().parents[2] / "resources" / "help"
_LOCALES = ("en", "ru", "zh", "pt_BR")

#: Keys the two rows own in every locale (labels + the zero-as-word rendering).
_COST_KEYS = (
    "judge_concurrency",
    "judge_run_call_ceiling",
    "judge_run_call_ceiling_unlimited",
)

_GROUP = "image_gallery_ai_test_judge_cost"
_MODELS_GROUP = "image_gallery_ai_models_test_judge_cost"


@pytest.fixture
def gallery_ai_store(monkeypatch):
    """Throwaway AI-settings + model-cache groups for the whole page."""
    monkeypatch.setattr(store_module, "_QS_GROUP", _GROUP)
    monkeypatch.setattr(ai_models, "_QS_GROUP", _MODELS_GROUP)
    settings = QSettings(store_module._QS_ORG, store_module._QS_APP)
    for group in (_GROUP, _MODELS_GROUP):
        settings.remove(group)
    yield
    for group in (_GROUP, _MODELS_GROUP):
        settings.remove(group)


@pytest.fixture
def dialog(qapp, gallery_ai_store, monkeypatch):
    """A real SettingsDialog with only the Image Gallery AI page wired."""
    from tabs.image_gallery.tests.test_settings_ai_providers import _build_dialog

    widget = _build_dialog(monkeypatch)
    try:
        yield widget
    finally:
        widget.close()
        widget.deleteLater()


def _settings_block(locale: str) -> dict:
    path = _I18N_ROOT / locale / "image_gallery.json"
    return json.loads(path.read_text(encoding="utf-8"))["image_gallery"]["settings"]


@pytest.fixture
def save_calls(monkeypatch):
    """Record every ``save_field`` call while keeping the real write."""
    calls: list[tuple[str, object]] = []
    original = AiSettingsStore.save_field

    def _record(self, name, value):
        calls.append((str(name), value))
        return original(self, name, value)

    monkeypatch.setattr(AiSettingsStore, "save_field", _record)
    # The page's ``_save_field`` swallows exceptions, so a recorder is the only
    # way to prove the row actually goes through the store helper.
    return calls


def _persisted(name: str):
    return getattr(AiSettingsStore().load(), name)


# -- the rows -----------------------------------------------------------------


def test_the_page_shows_both_judge_cost_rows(dialog):
    concurrency = dialog.gallery_ai_judge_concurrency
    ceiling = dialog.gallery_ai_judge_ceiling

    # A virgin store carries the shipped defaults, and the page shows them.
    assert concurrency.value() == JUDGE_CONCURRENCY_DEFAULT
    assert ceiling.value() == 0
    assert dialog.gallery_ai_judge_ceiling_label.text() == "Judge run call ceiling"
    assert (
        dialog.gallery_ai_judge_concurrency_label.text() == "Parallel judge requests"
    )
    assert dialog.page_gallery_ai.isAncestorOf(concurrency)
    assert dialog.page_gallery_ai.isAncestorOf(ceiling)


def test_a_stored_config_is_shown_on_open(gallery_ai_store, monkeypatch, qapp):
    """The page reflects the config, not the widget defaults."""
    from tabs.image_gallery.tests.test_settings_ai_providers import _build_dialog

    store = AiSettingsStore()
    store.save_field("judge_concurrency", 5)
    store.save_field("judge_run_call_ceiling", 240)

    widget = _build_dialog(monkeypatch)
    try:
        assert widget.gallery_ai_judge_concurrency.value() == 5
        assert widget.gallery_ai_judge_ceiling.value() == 240
        assert widget.gallery_ai_judge_ceiling.text() == "240"
    finally:
        widget.close()
        widget.deleteLater()


def test_the_parallel_width_writes_through_save_field(dialog, save_calls):
    dialog.gallery_ai_judge_concurrency.setValue(5)

    assert ("judge_concurrency", 5) in save_calls
    assert _persisted("judge_concurrency") == 5


def test_an_out_of_range_width_is_shown_clamped(dialog, save_calls):
    """99 is not storable: the control shows the 8 the store ended up with."""
    dialog.gallery_ai_judge_concurrency.setValue(99)

    assert dialog.gallery_ai_judge_concurrency.value() == JUDGE_CONCURRENCY_MAX
    assert dialog.gallery_ai_judge_concurrency.text() == str(JUDGE_CONCURRENCY_MAX)
    assert _persisted("judge_concurrency") == JUDGE_CONCURRENCY_MAX
    # The write went through the store helper, not a raw setValue on QSettings.
    assert ("judge_concurrency", JUDGE_CONCURRENCY_MAX) in save_calls


def test_the_shown_width_is_read_back_from_the_store(dialog, monkeypatch):
    """A refused write is never echoed: the control shows the STORE's answer.

    ``save_field`` is the owner of the clamp, so the page must ask it back
    instead of trusting the widget's own range — with the write dropped, the
    control has to fall back to the persisted value (3), not keep the input (5).
    """

    def _drop(self, name, value):
        return None

    monkeypatch.setattr(AiSettingsStore, "save_field", _drop)

    dialog.gallery_ai_judge_concurrency.setValue(5)

    assert _persisted("judge_concurrency") == JUDGE_CONCURRENCY_DEFAULT
    assert dialog.gallery_ai_judge_concurrency.value() == JUDGE_CONCURRENCY_DEFAULT


# -- the ceiling --------------------------------------------------------------


def test_a_ceiling_edit_persists(dialog, save_calls):
    dialog.gallery_ai_judge_ceiling.setValue(120)

    assert ("judge_run_call_ceiling", 120) in save_calls
    assert dialog.gallery_ai_judge_ceiling.text() == "120"
    assert _persisted("judge_run_call_ceiling") == 120


def test_a_zero_ceiling_renders_as_unlimited(dialog, qapp):
    dialog.gallery_ai_judge_ceiling.setValue(40)
    dialog.gallery_ai_judge_ceiling.setValue(0)
    # SpinBox writes str(value) after emitting valueChanged; the page restores
    # the word on the next event-loop turn.
    qapp.processEvents()

    assert _persisted("judge_run_call_ceiling") == 0
    assert dialog.gallery_ai_judge_ceiling.value() == 0
    assert dialog.gallery_ai_judge_ceiling.text() == "unlimited"


def test_a_negative_ceiling_is_floored_to_unlimited(dialog, qapp):
    dialog.gallery_ai_judge_ceiling.setValue(40)
    dialog.gallery_ai_judge_ceiling.setValue(-5)
    qapp.processEvents()

    assert _persisted("judge_run_call_ceiling") == 0
    assert dialog.gallery_ai_judge_ceiling.text() == "unlimited"


def test_the_unlimited_word_survives_a_focus_visit(dialog, qapp):
    """Clicking the field and leaving must not turn the word back into "0"."""
    dialog.gallery_ai_judge_ceiling.editingFinished.emit()
    qapp.processEvents()

    assert dialog.gallery_ai_judge_ceiling.text() == "unlimited"
    assert _persisted("judge_run_call_ceiling") == 0


# -- wiring -------------------------------------------------------------------


def test_the_payload_carries_both_judge_cost_settings(dialog):
    from plugins.settings.registry import get_settings_registry

    dialog.gallery_ai_judge_concurrency.setValue(4)
    dialog.gallery_ai_judge_ceiling.setValue(60)

    payload = get_settings_registry().read_payloads(dialog)["image_gallery.ai"]
    assert payload["judge_concurrency"] == 4
    assert payload["judge_run_call_ceiling"] == 60
    # The seeder mirrors the store, so the snapshot round-trips through it.
    seeded = get_settings_registry().seed_payloads(None)["image_gallery.ai"]
    assert seeded["judge_concurrency"] == 4
    assert seeded["judge_run_call_ceiling"] == 60


def test_the_two_rows_are_part_of_the_ai_search_group():
    from tabs.image_gallery.ui import settings_ai

    for key in _COST_KEYS:
        assert f"image_gallery.settings.{key}" in settings_ai.AI_GROUP.keys, key


# -- the locale bundles + help pages ------------------------------------------


@pytest.mark.parametrize("locale", _LOCALES)
def test_every_locale_carries_the_judge_cost_keys(locale):
    block = _settings_block(locale)

    for key in _COST_KEYS:
        value = str(block.get(key) or "").strip()
        assert value, f"{locale}: image_gallery.settings.{key} is empty"


@pytest.mark.parametrize("locale", ("ru", "zh", "pt_BR"))
def test_the_judge_cost_keys_are_really_translated(locale):
    english = _settings_block("en")
    block = _settings_block(locale)

    untranslated = [key for key in _COST_KEYS if block[key] == english[key]]
    assert not untranslated, f"{locale}: English fallback for {untranslated}"


@pytest.mark.parametrize("locale", _LOCALES)
def test_every_locale_explains_what_a_judge_run_costs(locale):
    """One sentence per row, in the page a user opens from Settings."""
    text = (_HELP_ROOT / locale / "ask_ai.md").read_text(encoding="utf-8").casefold()
    unlimited = str(_settings_block(locale)["judge_run_call_ceiling_unlimited"])

    assert unlimited.casefold() in text, locale
    assert "k" in text, locale
    # The per-row cost sentence: a lane is another request, a run is k per card.
    assert "card" in text or "карточ" in text or "卡片" in text or "cartõ" in text, locale
