"""Find Action member apply must not leak stale dialog widgets into the store.

Regression: ``DialogManager.apply_settings_member`` pushes
``dialog.get_settings()`` through the application service after activating a
single tagged control. The dialog is long-lived (the member path hides it,
never closes it), so its other widgets can hold state older than the store —
applying that whole snapshot would silently reset the values the store has
since (ui_mode -> beginner, ui_scale -> widget default, rhi -> default).
``sync_from_store`` before the member mutation re-seeds every covered widget
from the store, so only the activated member's change takes effect. The
``show_settings_dialog`` path must re-seed the same way before showing.
"""

from __future__ import annotations

from types import SimpleNamespace

from PySide6.QtWidgets import QApplication

from plugins.settings.dialog import SettingsDialog
from ui.managers.dialog_manager import DialogManager


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


class _FakeService:
    def __init__(self):
        self.applied = None

    def apply(self, data):
        self.applied = data


def test_member_apply_reseeds_dialog_before_mutation():
    """A store value newer than the dialog's widgets must survive a member
    apply on an unrelated control."""
    # Dialog built when the store said expert; the store has since moved to
    # advanced. Without the pre-apply sync the stale expert radio would leak
    # back into the store.
    dialog = _dialog(current_ui_mode="expert", current_ui_scale_factor=1.0)
    store = SimpleNamespace(
        settings=SimpleNamespace(
            ui_mode="advanced",
            ui_scale_factor=1.25,
            rhi_backend="vulkan",
            system_notifications_enabled=True,
            debug_mode_enabled=False,
        )
    )
    dialog.context.store = store
    service = _FakeService()
    host = SimpleNamespace(
        store=store,
        main_controller=None,
        event_bus=None,
        parent_widget=None,
        _settings_dialog=dialog,
        _settings_application_service=service,
    )

    activated = DialogManager(host).apply_settings_member(
        "builtin.general", "settings.appearance", "settings.enable_debug_logging"
    )
    assert activated is True

    assert service.applied is not None
    # The member's own change goes through (debug toggled False -> True)...
    assert service.applied.debug_enabled is True
    # ...but nothing else drifts from the dialog's stale build-time state.
    assert service.applied.ui_mode == "advanced"
    assert service.applied.ui_scale_factor == 1.25
    assert service.applied.rhi_backend == "vulkan"


def test_show_settings_dialog_reseeds_before_show(qtbot):
    """Re-showing the cached dialog must sync widgets from the store first.

    The dialog survives hide() (Find Action member path), so a re-show with
    drifted widget state would show — and later apply — stale values.
    """
    dialog = _dialog(current_ui_mode="expert", current_ui_scale_factor=1.0)
    store = SimpleNamespace(
        settings=SimpleNamespace(
            ui_mode="advanced",
            ui_scale_factor=1.25,
            rhi_backend="vulkan",
            system_notifications_enabled=True,
            debug_mode_enabled=False,
        )
    )
    dialog.context.store = store
    host = SimpleNamespace(
        store=store,
        main_controller=None,
        event_bus=None,
        parent_widget=None,
        _settings_dialog=dialog,
        _settings_application_service=object(),
    )

    synced = []
    original = dialog.sync_from_store
    dialog.sync_from_store = lambda: (synced.append(1), original())[1]

    manager = DialogManager(host)
    manager.show_settings_dialog()
    qtbot.addWidget(dialog)

    assert synced, "show path must re-seed the dialog from the store"
    assert dialog.get_settings().ui_mode == "advanced"
    assert dialog.get_settings().ui_scale_factor == 1.25
