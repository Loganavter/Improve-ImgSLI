"""Diagnostics plugin: bootstrap hooks, manual report action, crash content."""

from __future__ import annotations

import logging
import sys
import threading
from types import SimpleNamespace

import pytest
from PySide6.QtCore import qInstallMessageHandler

from core.plugin_coordinator import PluginCoordinator
from core.state_management.dispatcher import Dispatcher
from core.store import Store
from plugins.diagnostics import collect
from plugins.diagnostics.plugin import DiagnosticsPlugin

_LOG = logging.getLogger("ImproveImgSLI")


def _make_store() -> Store:
    store = Store()
    store.set_dispatcher(Dispatcher(store))
    return store


@pytest.fixture
def diag():
    """Provide a booted diagnostics plugin; restore global hooks afterwards."""
    saved_sys = sys.excepthook
    saved_thread = threading.excepthook
    booted: list[DiagnosticsPlugin] = []

    def _boot() -> tuple[DiagnosticsPlugin, Store]:
        store = _make_store()
        plugin = DiagnosticsPlugin()
        plugin.initialize(
            SimpleNamespace(store=store, event_bus=None, plugin_coordinator=None)
        )
        # Keep unit tests GUI-free: record scheduling instead of showing a
        # real dialog (the dialog is verified out-of-band via capture_surface).
        scheduled: list = []
        plugin._scheduled = scheduled  # type: ignore[attr-defined]
        plugin._schedule_dialog = scheduled.append  # type: ignore[assignment]
        booted.append(plugin)
        return plugin, store

    yield _boot

    for plugin in booted:
        try:
            plugin.shutdown()
        except Exception:
            pass
    sys.excepthook = saved_sys
    threading.excepthook = saved_thread
    try:
        qInstallMessageHandler(None)
    except Exception:
        pass


# --------------------------------------------------------------------------
# lifecycle / discovery
# --------------------------------------------------------------------------

def test_plugin_declares_bootstrap_tier() -> None:
    meta = DiagnosticsPlugin._plugin_meta
    assert meta["name"] == "diagnostics"
    assert meta["startup_tier"] == "bootstrap"


def test_discovery_scans_diagnostics_at_bootstrap_tier() -> None:
    from core.plugin_system.discovery_scan import iter_plugin_entry_points

    by_name = {e.plugin_name: e.startup_tier for e in iter_plugin_entry_points()}
    assert by_name.get("diagnostics") == "bootstrap"


def test_bootstrap_lifecycle_installs_and_restores_excepthooks(diag) -> None:
    plugin, _store = diag()
    assert sys.excepthook is plugin._excepthook
    assert threading.excepthook is plugin._thread_excepthook
    assert plugin._logring is not None

    plugin.shutdown()
    assert sys.excepthook is not plugin._excepthook
    assert threading.excepthook is not plugin._thread_excepthook


def test_bootstrap_tier_discovery_installs_hooks_after_initialize() -> None:
    coordinator = PluginCoordinator(event_bus=None)
    plugin = DiagnosticsPlugin()
    coordinator.register_plugins([plugin])
    store = _make_store()
    coordinator.initialize(
        SimpleNamespace(store=store, event_bus=None, plugin_coordinator=coordinator)
    )
    try:
        assert sys.excepthook is plugin._excepthook
    finally:
        plugin.shutdown()


# --------------------------------------------------------------------------
# manual action
# --------------------------------------------------------------------------

def test_manual_report_action_registered(diag) -> None:
    from ui.actions.registry import get_action_registry, reset_action_registry_for_tests

    reset_action_registry_for_tests()
    plugin, _store = diag()
    try:
        descriptor = get_action_registry().get("diagnostics.create_report")
        assert descriptor is not None
        assert descriptor.run is not None
    finally:
        reset_action_registry_for_tests()


def test_action_label_translated_in_all_languages() -> None:
    from pathlib import Path

    from resources.translations import add_i18n_root, tr

    add_i18n_root(Path("src/plugins/diagnostics/resources/i18n"))
    for lang in ("en", "ru", "zh", "pt_BR"):
        text = tr("diagnostics.action.create_report", lang)
        assert text and text != "diagnostics.action.create_report", lang


def test_handle_command_creates_report(diag) -> None:
    plugin, _store = diag()
    report = plugin.handle_command("create_report", show=False)
    assert report.payload["runtime"]["active_tab"] == "session_picker"
    assert report is plugin.last_report


# --------------------------------------------------------------------------
# forced unhandled exceptions
# --------------------------------------------------------------------------

def test_main_loop_exception_report_has_traceback_env_logs_tab(diag) -> None:
    plugin, _store = diag()
    _LOG.warning("DIAG-LOGRING-MARKER")
    # Isolate the plugin's own handling from the test harness's excepthook.
    plugin._previous_excepthook = None

    hook = sys.excepthook  # the plugin's installed sys.excepthook
    try:
        raise ValueError("boom-main-xyz")
    except ValueError:
        hook(*sys.exc_info())

    assert plugin.last_report is not None
    report = plugin.last_report
    assert "ValueError: boom-main-xyz" in report.text
    assert "Traceback" in report.text
    assert report.payload["failure"]["source"] == "main"
    assert report.payload["environment"]  # env snapshot present
    assert report.payload["runtime"]["active_tab"] == "session_picker"
    assert any("DIAG-LOGRING-MARKER" in line for line in report.payload["logs"])
    assert plugin._scheduled  # the report was offered to the user


def test_thread_exception_report_captures_thread_and_traceback(diag) -> None:
    plugin, _store = diag()
    # Isolate from the test harness's threading.excepthook (pytest's capture).
    plugin._previous_thread_excepthook = None

    def _boom() -> None:
        raise RuntimeError("boom-thread-xyz")

    thread = threading.Thread(target=_boom, name="diag-worker")
    thread.start()
    thread.join()

    assert plugin.last_report is not None
    report = plugin.last_report
    assert "RuntimeError: boom-thread-xyz" in report.text
    assert report.payload["failure"]["source"] == "thread"
    assert report.payload["failure"]["thread"] == "diag-worker"
    assert plugin._scheduled


def test_report_has_no_image_field_after_crash(diag) -> None:
    plugin, _store = diag()
    plugin._previous_excepthook = None
    try:
        raise KeyError("k")
    except KeyError:
        sys.excepthook(*sys.exc_info())

    def _keys(node):
        keys = set()
        if isinstance(node, dict):
            for key, value in node.items():
                keys.add(str(key).lower())
                keys |= _keys(value)
        elif isinstance(node, list):
            for item in node:
                keys |= _keys(item)
        return keys

    assert _keys(plugin.last_report.payload).isdisjoint(
        {"image", "pixmap", "screenshot", "preview", "pixels"}
    )


def test_breadcrumbs_record_dispatches(diag) -> None:
    from core.state_management.viewport_actions import SetSplitPositionAction

    plugin, store = diag()
    store.get_dispatcher().dispatch(SetSplitPositionAction(0.3))
    labels = [crumb.label for crumb in plugin.breadcrumbs.snapshot()]
    assert any("SPLIT" in label.upper() for label in labels), labels


def test_env_snapshot_has_display_and_gpu_fields() -> None:
    env = collect.collect_environment()
    machine = collect.collect_machine()
    assert "session_type" in env
    assert "display_server" in env
    assert "rhi_backend" in machine
    assert "gpu" in machine


def test_report_preview_is_read_only_code_text_in_a_host_scroll_area(qapp) -> None:
    """The preview is ``Text(mode="code")`` (read-only) — the same painted
    buffer ``TextView`` wrapped, with the scroll area now composed by the
    dialog. Report text and the Copy action must stay identical.
    """
    from PySide6.QtGui import QGuiApplication

    from plugins.diagnostics.dialog import DiagnosticsDialog
    from plugins.diagnostics.report import DiagnosticsReport
    from sli_ui_toolkit.widgets import SurfaceScrollArea, Text

    text = "diagnostics line\n" * 5
    report = DiagnosticsReport(payload={"app": {"version": "test"}}, text=text)
    dialog = DiagnosticsDialog(report, current_language="en")
    try:
        dialog.show()
        qapp.processEvents()

        preview = dialog.preview
        assert isinstance(preview, Text)
        assert preview.mode() == "code"
        assert preview.is_editing() is False
        assert preview.plain_text() == text
        assert isinstance(dialog.preview_scroll, SurfaceScrollArea)
        assert dialog.preview_scroll.widget() is preview

        dialog._copy()
        assert QGuiApplication.clipboard().text() == text
    finally:
        dialog.close()
