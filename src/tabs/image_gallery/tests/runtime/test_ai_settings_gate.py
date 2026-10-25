"""The enable checkbox is the permission gate for every control below it.

Owner's rule (2026-10-25): while "Enable AI image analysis" is unticked, nothing
on the page may look editable — every provider/URL/key/model/cost control is a
way to spend the permission, and the page used to offer them all as live.

The checkbox itself never disables: it is the thing you tick to unlock them.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QSettings

from tabs.image_gallery.services import ai_settings_store as store_module
from tabs.image_gallery.services.ai_settings_store import AiSettingsStore

_GROUP = store_module._QS_GROUP
_MODELS_GROUP = "image_gallery_ai_models"


@pytest.fixture
def clean_store(qapp):
    settings = QSettings(store_module._QS_ORG, store_module._QS_APP)
    for group in (_GROUP, _MODELS_GROUP):
        settings.remove(group)
    yield
    for group in (_GROUP, _MODELS_GROUP):
        settings.remove(group)


@pytest.fixture
def build(clean_store, monkeypatch):
    from tabs.image_gallery.tests.test_settings_ai_providers import _build_dialog

    def _build(enabled: bool):
        AiSettingsStore().save_field("enabled", enabled)
        dialog = _build_dialog(monkeypatch)
        return dialog

    return _build


def test_unticked_checkbox_disables_everything_below_it(build):
    dialog = build(enabled=False)
    try:
        assert dialog.gallery_ai_enabled.isChecked() is False
        gated = dialog.gallery_ai_gated_controls
        assert gated, "the page must expose the gated list"
        still_live = [w for w in gated if w.isEnabled()]
        assert still_live == [], (
            "these controls are live while AI is disabled: "
            f"{[type(w).__name__ for w in still_live]}"
        )
    finally:
        dialog.close()
        dialog.deleteLater()


def test_ticking_it_unlocks_them_and_unticking_locks_them_again(build):
    dialog = build(enabled=False)
    try:
        dialog.gallery_ai_enabled.setChecked(True)
        assert all(w.isEnabled() for w in dialog.gallery_ai_gated_controls)

        dialog.gallery_ai_enabled.setChecked(False)
        assert not any(w.isEnabled() for w in dialog.gallery_ai_gated_controls)
    finally:
        dialog.close()
        dialog.deleteLater()


def test_an_enabled_profile_starts_unlocked(build):
    dialog = build(enabled=True)
    try:
        assert dialog.gallery_ai_enabled.isChecked() is True
        assert all(w.isEnabled() for w in dialog.gallery_ai_gated_controls)
    finally:
        dialog.close()
        dialog.deleteLater()
