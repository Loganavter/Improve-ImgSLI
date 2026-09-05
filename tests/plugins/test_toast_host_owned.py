"""Host-owned ToastManager: LayoutPlugin owns a non-None toast manager after setup.

Dogma source: docs/dev/plan_toast_refactor.md (Phase 3 regression tests;
§2.1 row 1 — every toast path funnels into ``window.toast_manager`` — and
§3.1 — ``LayoutPlugin`` creates ``ToastManager(parent_window)`` with anchor
``None`` allowed per toolkit ``FEEDBACK_API.md``).
"""

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QWidget

from plugins.layout.plugin import LayoutPlugin
from sli_ui_toolkit.widgets import ToastManager

APP = QApplication.instance() or QApplication([])


def test_setup_ui_reference_without_canvas_pages_owns_toast_manager():
    # Path choice: this exercises the REAL LayoutPlugin.setup_ui_reference
    # (not a hand-built ToastManager), because the bug is precisely its
    # one-shot race — tab-owned layout_manager is None while
    # ImageCompareTab._widget is unset (lazy pages; only session_picker
    # exists at setup), so window.toast_manager stayed None forever.
    # The registry is a process-wide singleton shared with every other
    # test in the process: if some earlier test materialized a canvas page,
    # a provider could answer and manager would be non-None for the wrong
    # reason. The assertion therefore pins only the host-owned contract
    # (toast_manager is not None), never which provider answered, so it
    # stays meaningful under either registry state. Fragility note: run
    # order against tests that open real canvas tabs can flip *why* this
    # passes, but never *whether* the contract holds post-fix.
    plugin = LayoutPlugin()
    assert plugin.store is None  # fresh: no initialize(), no Store involved
    parent = QWidget()
    try:
        plugin.setup_ui_reference(SimpleNamespace(), parent)
        assert plugin.toast_manager is not None
    finally:
        parent.deleteLater()


def test_host_toast_manager_show_update_close_round_trip_offscreen():
    parent = QWidget()
    try:
        manager = ToastManager(parent)  # anchor None: valid per FEEDBACK_API.md
        toast_id = manager.show_toast("Saving", duration=0, progress=0)
        assert isinstance(toast_id, int)
        # update/close must not raise offscreen (placement math swallows
        # anchor errors per the toolkit's guards).
        manager.update_toast(toast_id, "Saving", success=False, duration=0, progress=50)
        manager.update_toast(toast_id, "Done", success=True, duration=2000, progress=100)
        manager.close_toast(toast_id)
    finally:
        parent.deleteLater()
