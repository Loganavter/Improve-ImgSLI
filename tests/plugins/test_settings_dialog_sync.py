"""Settings dialog sync_from_store/get_settings roundtrip must not drift.

Regression: ``get_settings`` resolved the UI-mode radios with a dict that
missed the beginner radio, and ``sync_from_store`` re-synced only the
notification/debug checkboxes — the Find Action member path hides the
dialog without deleting it, so on a later show the mode radios / scale
slider / rhi combo could carry stale widget state. Clicking OK then pushed
the *widget defaults* (ui_mode -> "beginner", rhi_backend -> "default")
over the persisted values, silently resetting them.
"""

from __future__ import annotations

from types import SimpleNamespace

from PySide6.QtWidgets import QApplication

from plugins.settings.dialog import SettingsDialog
from plugins.settings.models import SettingsDialogData


def _dialog(**overrides) -> SettingsDialog:
    QApplication.instance() or QApplication([])
    kwargs = dict(
        current_language="en",
        current_theme="dark",
        current_max_length=30,
        min_limit=1,
        max_limit=200,
        debug_mode_enabled=False,
        system_notifications_enabled=True,
        current_resolution_limit=0,
        active_tab="image_compare",
    )
    kwargs.update(overrides)
    return SettingsDialog(**kwargs)


def test_ui_mode_radios_resolve_all_modes():
    dialog = _dialog()
    # Default (no radio forced): resolves to beginner, never a crash.
    data = dialog.get_settings()
    assert data.ui_mode == "beginner"

    dialog.radio_ui_mode_beginner.setChecked(True)
    assert dialog.get_settings().ui_mode == "beginner"
    dialog.radio_ui_mode_advanced.setChecked(True)
    assert dialog.get_settings().ui_mode == "advanced"
    dialog.radio_ui_mode_expert.setChecked(True)
    assert dialog.get_settings().ui_mode == "expert"


def test_sync_from_store_restores_mode_scale_and_rhi():
    dialog = _dialog(
        current_ui_mode="expert",
        current_ui_scale_factor=1.5,
        rhi_backend="opengl",
    )
    store = SimpleNamespace(
        settings=SimpleNamespace(
            ui_mode="advanced",
            ui_scale_factor=1.25,
            rhi_backend="vulkan",
            system_notifications_enabled=False,
            debug_mode_enabled=False,
        )
    )
    dialog.context.store = store
    dialog.sync_from_store()

    data = dialog.get_settings()
    assert data.ui_mode == "advanced", "stale radio must not survive re-sync"
    assert data.ui_scale_factor == 1.25, "scale slider must track the store"
    assert data.rhi_backend == "vulkan", "rhi combo must track the store"


def test_sync_from_store_restores_mode_via_reused_dialog():
    """The Find Action member path hides (not closes) the dialog; a re-show
    must re-seed every get_settings source, not just the checkboxes."""
    dialog = _dialog(current_ui_mode="expert", current_ui_scale_factor=1.0)
    store = SimpleNamespace(
        settings=SimpleNamespace(
            ui_mode="expert",
            ui_scale_factor=1.0,
            rhi_backend="opengl",
            system_notifications_enabled=True,
            debug_mode_enabled=False,
        )
    )
    dialog.context.store = store
    dialog.sync_from_store()

    # Simulate user flipping the mode radio to beginner, then a re-sync
    # (the dialog gets hidden and re-shown — store still says expert).
    dialog.radio_ui_mode_beginner.setChecked(True)
    dialog.sync_from_store()
    assert dialog.get_settings().ui_mode == "expert"

    # And a scale drift on the slider must be undone by the re-sync too.
    dialog.slider_ui_scale.setValue(200)
    dialog.sync_from_store()
    assert dialog.get_settings().ui_scale_factor == 1.0

    # get_settings output feeds SettingsApplicationService.apply unchanged.
    data = dialog.get_settings()
    assert isinstance(data, SettingsDialogData)
