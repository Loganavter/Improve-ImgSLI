"""Live UI scale apply: settings dialog -> service -> UiScale -> chrome reflow.

Covers the archived UI-scale plan's Phase 2.4 chain: changing the Interface
Scale spinbox and confirming the settings service applies the factor to the
store, the toolkit UiScale singleton, and live widget geometry (CSD menu
strip + dialog action bar) — forward and back to 1.0.
"""

from __future__ import annotations

import sys

import pytest
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget

from core.state_management.reducers import SettingsReducer
from core.store import Store
from shared_toolkit.ui.managers.font_manager import FontManager
from plugins.settings.application_service import SettingsApplicationService
from plugins.settings.dialog import SettingsDialog
from plugins.settings.models import SettingsDialogData
from ui.main_window.csd_menu_strip import (
    ContextMenuAction,
    CsdMenuSpec,
    CsdMenuStrip,
)
from ui.widgets.form_controls import DialogActionBar


def _make_dialog(store) -> SettingsDialog:
    return SettingsDialog(
        current_language="en",
        current_theme=store.settings.theme,
        current_max_length=30,
        min_limit=1,
        max_limit=200,
        debug_mode_enabled=False,
        system_notifications_enabled=True,
        current_ui_scale_factor=1.0,
        active_tab="image_compare",
    )


class _FakeDispatcher:
    def __init__(self, store):
        self.store = store

    def dispatch(self, action, scope=None):
        self.store.settings = SettingsReducer.reduce(self.store.settings, action)


def _build_chrome() -> tuple[CsdMenuStrip, DialogActionBar, QWidget]:
    strip = CsdMenuStrip(
        [
            CsdMenuSpec(
                label="File",
                entries=[ContextMenuAction("open", "Open", shortcut="Ctrl+O")],
                on_triggered=lambda *_: None,
            ),
            CsdMenuSpec(
                label="Help",
                entries=[ContextMenuAction("about", "About")],
                on_triggered=lambda *_: None,
            ),
        ]
    )
    bar = DialogActionBar("OK", "Cancel")
    host = QWidget()
    layout = QVBoxLayout(host)
    layout.addWidget(strip)
    layout.addWidget(bar)
    host.show()
    return strip, bar, host


def test_ui_scale_live_apply_roundtrip(qtbot):
    app = QApplication.instance() or QApplication([])
    store = Store()
    store.get_dispatcher = lambda: _FakeDispatcher(store)

    # Startup-order simulation: ApplyFontSettingsStep pins the app font
    # before any chrome is built (otherwise the first settings apply swaps
    # the font mid-test and skews size comparisons).
    FontManager.get_instance().apply_from_state(store)
    app.processEvents()

    strip, bar, host = _build_chrome()
    qtbot.addWidget(host)
    app.processEvents()

    from sli_ui_toolkit.managers import UiScale

    before = (
        strip.height(),
        strip._buttons[0].size().toTuple(),
        bar.height(),
    )

    dialog = _make_dialog(store)
    qtbot.addWidget(dialog)
    svc = SettingsApplicationService(store, None, None)

    # Slider value = factor * 100 (50..250 → 0.50..2.50, free step 0.01).
    dialog.slider_ui_scale.setValue(150)
    svc.apply(dialog.get_settings())
    app.processEvents()

    assert abs(store.settings.ui_scale_factor - 1.5) < 1e-9
    assert abs(UiScale.get_instance().factor() - 1.5) < 1e-9
    scaled_strip_h = round(before[0] * 1.5)
    scaled_btn = (round(before[1][0] * 1.5), round(before[1][1] * 1.5))
    assert strip.height() == scaled_strip_h
    assert strip._buttons[0].size().toTuple() == scaled_btn
    # The bar grows to fit its scaled minimums (text-height component may
    # scale differently, so assert growth + no clipping, not exact ratio).
    assert bar.height() >= round(before[2] * 1.5) - 3
    assert bar.height() > before[2]

    dialog.slider_ui_scale.setValue(100)
    svc.apply(dialog.get_settings())
    app.processEvents()

    assert abs(UiScale.get_instance().factor() - 1.0) < 1e-9
    after = (strip.height(), strip._buttons[0].size().toTuple(), bar.height())
    assert after == before, (before, after)

    dialog.close()