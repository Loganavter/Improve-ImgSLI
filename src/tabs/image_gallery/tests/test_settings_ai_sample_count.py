"""AI settings page: the judge's run count (k) is a real, saved choice.

The store half landed with ``AiSettings.sample_count`` (choices 1/2/3/5, default
3, part of the analyze cache identity) but the page had no control — k could
only be changed by editing the INI by hand. This file pins the control, its
persistence path, the cost hint, and the four locale payloads.

RED BEFORE: the pre-change page had no ``gallery_ai_samples`` combo, no
``gallery_ai_samples_hint`` caption and no ``sample_count`` key in the settings
payload reader, so every test here fails on the parent commit with
``AttributeError`` / ``KeyError``.

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
    SAMPLE_COUNT_CHOICES,
    AiSettingsStore,
)

_I18N_ROOT = Path(__file__).resolve().parents[1] / "resources" / "i18n"
_LOCALES = ("en", "ru", "zh", "pt_BR")

#: Keys the control owns in every locale (label + one per choice + the hint).
_SAMPLE_KEYS = (
    "sample_count",
    "sample_count_1",
    "sample_count_2",
    "sample_count_3",
    "sample_count_5",
    "sample_count_hint",
)

#: Phrases that would promise a stable ordering. Measured on near-identical
#: variants: the order still flips at k=1 (68%), k=2 (61%) and k=3 (54%), so a
#: hint that promises one would be a lie the UI cannot keep.
_ORDER_PROMISES = (
    "stable order",
    "same order",
    "always order",
    "guarantee",
    "will rank",
    "will order",
    "fix the order",
)


@pytest.fixture
def gallery_ai_store(monkeypatch):
    """Throwaway AI-settings + model-cache groups for the whole page."""
    monkeypatch.setattr(store_module, "_QS_GROUP", "image_gallery_ai_test_samples")
    monkeypatch.setattr(ai_models, "_QS_GROUP", "image_gallery_ai_models_test_samples")
    settings = QSettings(store_module._QS_ORG, store_module._QS_APP)
    for group in ("image_gallery_ai_test_samples", "image_gallery_ai_models_test_samples"):
        settings.remove(group)
    yield
    for group in ("image_gallery_ai_test_samples", "image_gallery_ai_models_test_samples"):
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


def _choice_index(value: int) -> int:
    return list(SAMPLE_COUNT_CHOICES).index(value)


def _settings_block(locale: str) -> dict:
    path = _I18N_ROOT / locale / "image_gallery.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload["image_gallery"]["settings"]


def test_the_page_exposes_the_judge_run_count(dialog):
    combo = dialog.gallery_ai_samples

    assert [combo.itemData(i) for i in range(combo.count())] == list(
        SAMPLE_COUNT_CHOICES
    )
    # A virgin store carries the shipped default, and the page shows it.
    assert combo.currentData() == 3


def test_the_run_count_is_part_of_the_ai_search_group():
    from tabs.image_gallery.ui import settings_ai

    assert "image_gallery.settings.sample_count" in settings_ai.AI_GROUP.keys
    for key in _SAMPLE_KEYS[1:]:
        assert f"image_gallery.settings.{key}" in settings_ai.AI_GROUP.keys


def test_selecting_a_run_count_persists_it(dialog):
    dialog.gallery_ai_samples.setCurrentIndex(_choice_index(5))

    # The store is the single owner of the value: a page rebuild reads it back.
    assert AiSettingsStore().load().sample_count == 5


def test_the_payload_carries_the_run_count(dialog):
    from plugins.settings.registry import get_settings_registry

    dialog.gallery_ai_samples.setCurrentIndex(_choice_index(2))

    payload = get_settings_registry().read_payloads(dialog)["image_gallery.ai"]
    assert payload["sample_count"] == 2
    # The seeder mirrors the store, so the snapshot round-trips through it.
    seeded = get_settings_registry().seed_payloads(None)["image_gallery.ai"]
    assert seeded["sample_count"] == 2


def test_a_run_count_change_moves_the_apply_identity(dialog):
    """Apply compares analysis identities — k must be in the one it snapshots.

    The same identity is the disk-cache key, so a k change also turns the old
    scorecards into MISSes (re-drawn at the new k) instead of serving them.
    """
    from types import SimpleNamespace

    from tabs.image_gallery.services.ai_settings_store import AiSettingsStore
    from tabs.image_gallery.ui import settings_ai

    owner = SimpleNamespace(
        _ai_settings_store=AiSettingsStore(),
        state=SimpleNamespace(mode="camera"),
    )
    before = settings_ai._identity_snapshot(owner)
    assert before is not None and before["k"] == "3"

    dialog.gallery_ai_samples.setCurrentIndex(_choice_index(5))

    after = settings_ai._identity_snapshot(owner)
    assert after is not None and after["k"] == "5"
    assert before != after


def test_the_hint_states_the_cost_per_card_and_follows_the_choice(dialog):
    hint = dialog.gallery_ai_samples_hint
    default_text = hint.text().lower()
    assert "image call" in default_text
    assert "cost" in default_text
    assert "3" in default_text

    dialog.gallery_ai_samples.setCurrentIndex(_choice_index(5))

    text = dialog.gallery_ai_samples_hint.text().lower()
    assert "5" in text
    assert "image call" in text


def test_the_hint_never_promises_a_stable_order(dialog):
    text = dialog.gallery_ai_samples_hint.text().lower()
    promised = [phrase for phrase in _ORDER_PROMISES if phrase in text]
    assert not promised, f"the hint promises an order the judge cannot keep: {promised}"


def test_the_label_fits_its_text(dialog):
    from PySide6.QtGui import QFontMetrics

    label = dialog.gallery_ai_samples_label
    need = QFontMetrics(label.font()).horizontalAdvance(label.text())
    assert label.width() >= need, (label.text(), label.width(), need)


def test_the_control_and_hint_use_the_page_typography(dialog):
    from plugins.settings.typography import SETTINGS_BODY_PX, SETTINGS_CAPTION_PX

    assert dialog.gallery_ai_samples.font().pixelSize() == SETTINGS_BODY_PX
    assert dialog.gallery_ai_samples_hint.font().pixelSize() == SETTINGS_CAPTION_PX
    # Both live on the AI page — the hint sits under the picker, in the group.
    assert dialog.page_gallery_ai.isAncestorOf(dialog.gallery_ai_samples)
    assert dialog.page_gallery_ai.isAncestorOf(dialog.gallery_ai_samples_hint)


def test_every_locale_carries_the_same_settings_keys():
    reference = set(_settings_block("en"))
    for locale in _LOCALES:
        block = _settings_block(locale)
        missing = sorted(reference - set(block))
        assert not missing, f"{locale}: missing settings keys {missing}"
        for key in _SAMPLE_KEYS:
            value = str(block.get(key) or "").strip()
            assert value, f"{locale}: image_gallery.settings.{key} is empty"


@pytest.mark.parametrize("locale", _LOCALES)
def test_the_hint_keeps_its_count_placeholder(locale):
    assert "{count}" in _settings_block(locale)["sample_count_hint"]


@pytest.mark.parametrize("locale", ("ru", "zh", "pt_BR"))
def test_the_run_count_keys_are_really_translated(locale):
    english = _settings_block("en")
    block = _settings_block(locale)
    fallbacks = [key for key in _SAMPLE_KEYS if block[key] == english[key]]
    assert not fallbacks, f"{locale}: English fallback for {fallbacks}"
