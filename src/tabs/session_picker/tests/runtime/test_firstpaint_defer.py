"""First-paint deferral: deferred startup block + the shelf's one disk pass.

Cold-start recon (2026-10-24, ``task-startup-firstpaint-block-2026-10-24``):
``MainWindowStartupRuntime.emit_visual_ready`` armed
``_load_deferred_startup_modules`` with a 0-timer from inside the startup
pipeline, and ``MainWindowStartupController.show`` then drained pending 0-timers
with four ``processEvents`` passes. So plugin/tab discovery ran while nothing
was on screen yet, and the first paint waited for it.

The shelf half of ``#637`` was only half-effective for the same reason:
``refresh(verify_disk=False)`` skipped the stat at construction, but
``showEvent -> on_page_shown -> soft_refresh`` recomputed ``_live_state`` (one
``os.stat`` per record) regardless, and the deferred ``verify_disk_now`` pass
was another 0-timer the same drain fired. On a shared path thousands of
sub-80 ms syscalls are exactly the shape of a multi-second freeze.

Contracts pinned here:

* zero fingerprint stats between page construction and the first paint, then
  exactly ONE deferred pass (released by that paint);
* ``soft_refresh(verify_disk=False)`` — and an unverified (pending) shelf —
  never stats, so ``showEvent`` cannot start a second pass;
* the deferred startup block runs after the show-drain, not inside it;
* the startup trace carries paint.first_frame, titlebar.remeasure,
  shelf.show_event and shelf.disk_verify.

Stats are counted at the one funnel (``refresh_uc._disk_fingerprint``), which
is the per-record pass under test; the visible cards' own ``is_file()`` badge
check is O(visible), not O(records), and is out of scope here.
"""

from __future__ import annotations

import logging
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from types import SimpleNamespace

import pytest
from PySide6.QtCore import QSize

from core.log_names import APP_LOGGER_NAME
from core.startup_trace import reset_startup_trace
from services.io.recent_projects import RecentProjectRecord
from tabs.session_picker.recent.use_cases import refresh as refresh_uc
from tabs.session_picker.widget import SessionPickerWidget
from ui.main_window.lifecycle import MainWindowStartupController
from ui.main_window.startup import MainWindowStartupRuntime

_PANEL = "tabs.session_picker.recent.panel"
SPAN_LOGGER = f"{APP_LOGGER_NAME}.startup"
RECORD_COUNT = 1000


@pytest.fixture(autouse=True)
def _trace_clock():
    reset_startup_trace()
    yield
    reset_startup_trace()


class _FakeContext:
    """Minimal tab context (same shape the sibling picker tests use)."""

    def _tr(self, key: str, default: str = "") -> str:
        return default or key

    def call_service(self, name: str, *args, **kwargs):
        if name == "list_session_blueprints":
            return ()
        if name == "get_tab_icon":
            return None
        raise RuntimeError(f"unexpected service: {name}")

    def get_active_session(self):
        return None


def _records(count: int, tmp_path) -> list[RecentProjectRecord]:
    return [
        RecentProjectRecord(
            path=str(tmp_path / f"r{i}.imgsli"),
            display_name=f"r{i}",
            opened_at="2026-01-01T00:00:00+00:00",
            session_types=("image_compare",),
        )
        for i in range(count)
    ]


def _patch_recent_store(monkeypatch, records) -> None:
    monkeypatch.setattr(f"{_PANEL}.list_recent_projects", lambda **kwargs: list(records))
    monkeypatch.setattr(
        f"{_PANEL}.sort_recent_projects", lambda recs, **kwargs: list(recs)
    )
    monkeypatch.setattr(f"{_PANEL}.get_recent_view_mode", lambda **kwargs: "grid")
    monkeypatch.setattr(f"{_PANEL}.get_recent_sort_mode", lambda **kwargs: "recent")
    monkeypatch.setattr(f"{_PANEL}.get_recent_sort_order", lambda **kwargs: "desc")


def _span_lines(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.name == SPAN_LOGGER]


def _span_index(spans: list[str], fragment: str) -> int:
    return next((i for i, line in enumerate(spans) if fragment in line), -1)


def test_page_paints_before_the_one_disk_pass(
    qapp, qtbot, caplog, tmp_path, monkeypatch
):
    """No fingerprint stat between construction and first paint; one after."""
    monkeypatch.setenv("IMGSLI_STARTUP_TRACE", "1")
    caplog.set_level(logging.INFO, logger=SPAN_LOGGER)
    _patch_recent_store(monkeypatch, _records(RECORD_COUNT, tmp_path))
    statted: list[str] = []

    def _fingerprint(path: str):
        statted.append(path)
        return (True, 1)

    monkeypatch.setattr(refresh_uc, "_disk_fingerprint", _fingerprint)

    widget = SessionPickerWidget(context=_FakeContext())
    qtbot.addWidget(widget)
    recent = widget._recent_panel
    assert recent is not None
    # Construction rendered the stored records without touching the disk.
    assert statted == [], "page construction stat'ed the recent records"
    assert recent._disk_snapshot is None, "an unverified shelf must not claim a snapshot"
    assert recent._disk_verify_pending is True, "the one pass must stay armed"

    # The page rides the main window's first-frame gate; here the page is the
    # top-level window, so its own (real) runtime is the gate.
    runtime = MainWindowStartupRuntime(widget)
    widget.startup_runtime = runtime

    widget.show()
    # showEvent runs before the first paint and must not start the pass.
    assert statted == [], "showEvent (pre-paint) stat'ed the recent records"
    assert recent._disk_snapshot is None
    qapp.processEvents()
    assert statted == [], (
        "the disk pass ran before the first frame was presented (event loop "
        "turn incl. the paint is not a first-frame release)"
    )

    runtime.notify_first_frame_presented()
    qtbot.waitUntil(lambda: recent._disk_snapshot is not None, timeout=5000)
    assert len(statted) == RECORD_COUNT, (
        "the deferred pass must fingerprint every record exactly once; "
        f"observed {len(statted)} stats for {RECORD_COUNT} records"
    )
    assert len(set(statted)) == RECORD_COUNT, "a record was stat'ed twice"
    assert recent._disk_verify_pending is False
    assert recent._disk_snapshot is not None

    spans = _span_lines(caplog)
    show_index = _span_index(spans, "shelf.show_event")
    verify_index = _span_index(spans, "shelf.disk_verify")
    assert show_index >= 0, f"no shelf show-event span: {spans}"
    assert verify_index >= 0, f"no deferred disk-verify span: {spans}"
    assert show_index < verify_index, (
        "the disk pass must be measured after showEvent, not inside it: "
        f"{spans}"
    )


class _Items:
    def apply_selection(self) -> None:
        pass


class _PanelStub:
    def __init__(self) -> None:
        self._view_mode = "grid"
        self._sort_mode = "recent"
        self._sort_order = "desc"
        self._records: list = []
        self._selected_paths: set = set()
        self._disk_snapshot = None
        self._layout_ready = True
        self._items = _Items()
        self.rebuilds = 0

    def _rebuild_items(self) -> None:
        self.rebuilds += 1

    def _sync_header_controls(self) -> None:
        pass

    def _sync_opaque_fills(self) -> None:
        pass


def test_soft_refresh_skips_the_stat_pass_until_verified(tmp_path, monkeypatch):
    """``verify_disk=False`` and a pending shelf both skip the fingerprint pass."""
    records = _records(5, tmp_path)
    _patch_recent_store(monkeypatch, records)
    live_calls: list[int] = []
    monkeypatch.setattr(
        refresh_uc, "_live_state", lambda recs: live_calls.append(len(recs)) or []
    )

    panel = _PanelStub()
    refresh_uc.soft_refresh(panel, verify_disk=False)
    assert live_calls == [], "verify_disk=False still fingerprinted the records"
    assert panel._disk_snapshot is None, "unverified state must stay unverified"

    # A shelf whose deferred pass has not been released yet is unverified even
    # for a default call (this is the showEvent-before-first-paint case).
    panel._disk_verify_pending = True
    refresh_uc.soft_refresh(panel)
    assert live_calls == [], "a pending first-paint pass must own the only disk read"

    # Released (first paint done): the return-to-picker pass runs again.
    panel._disk_verify_pending = False
    panel._disk_snapshot = [("x", True, 1)]
    refresh_uc.soft_refresh(panel)
    assert live_calls == [5], "a verified shelf must detect external changes on return"


class _Signal:
    def __init__(self, sink: list) -> None:
        self._sink = sink

    def emit(self) -> None:
        self._sink.append("visual_ready")


def _startup_window(loads: list) -> SimpleNamespace:
    window = SimpleNamespace(
        startupVisualReady=_Signal(loads),
        _startup_visual_ready_emitted=False,
        _deferred_startup_loaded=False,
        _application_initialized=True,  # skip the startup pipeline
        _menu_controller=None,
        _custom_title_bar=None,
        ui=None,
        show=lambda: loads.append("show"),
        size=lambda: QSize(800, 600),
        isMaximized=lambda: False,
        layout=lambda: None,
    )
    runtime = MainWindowStartupRuntime(window)
    runtime._load_deferred_startup_modules = lambda: loads.append("deferred")
    window.startup_runtime = runtime
    return window


def test_deferred_block_waits_for_the_presented_frame(qapp):
    loads: list = []
    window = _startup_window(loads)
    runtime = window.startup_runtime

    runtime.emit_visual_ready()
    qapp.processEvents()
    assert loads == ["visual_ready"], (
        "the deferred startup block ran before the first frame was presented: "
        f"{loads}"
    )

    runtime.notify_first_frame_presented()
    qapp.processEvents()
    assert loads == ["visual_ready", "deferred"]

    # Idempotent: a second notify must not replay the block.
    runtime.notify_first_frame_presented()
    qapp.processEvents()
    assert loads == ["visual_ready", "deferred"]


def test_show_drain_does_not_run_the_deferred_block(
    qapp, caplog, monkeypatch
):
    """``show()`` paints frame 1 first, then releases the deferred block."""
    monkeypatch.setenv("IMGSLI_STARTUP_TRACE", "1")
    monkeypatch.setattr("plugins.onboarding.host.prepare_after_show", lambda w: None)
    caplog.set_level(logging.INFO, logger=SPAN_LOGGER)

    loads: list = []
    window = _startup_window(loads)
    window.startup_runtime.emit_visual_ready()

    MainWindowStartupController().show(window)

    assert loads == ["visual_ready", "show"], (
        "the deferred startup block ran inside show()'s drain (before the "
        f"first frame was presented): {loads}"
    )
    spans = _span_lines(caplog)
    assert _span_index(spans, "titlebar.remeasure") >= 0, (
        f"no titlebar remeasure span: {spans}"
    )
    assert _span_index(spans, "paint.first_frame") >= 0, (
        f"the startup trace has no first-frame boundary: {spans}"
    )
    assert _span_index(spans, "titlebar.remeasure") < _span_index(
        spans, "paint.first_frame"
    ), "the title bar must be remeasured before the first frame is marked"

    qapp.processEvents()
    assert loads == ["visual_ready", "show", "deferred"], (
        "the deferred block must be released on the first turn after show()"
    )


def test_release_after_the_page_was_destroyed_is_a_no_op(qapp, tmp_path, monkeypatch):
    """The first-frame queue outlives its page; a dead page must be forgotten.

    Falsification (pre-fix tree): delete the page, then run the queued release —
    ``verify_disk_now`` reaches ``_sync_opaque_fills`` and raises
    ``RuntimeError: Internal C++ object (SessionPickerWidget) already deleted``.
    This is exactly how a stale release crashed an unrelated later test in the
    full suite (``tests/runtime/test_dialog_title_bar_nav.py``).
    """
    from shiboken6 import delete, isValid

    _patch_recent_store(monkeypatch, _records(3, tmp_path))
    widget = SessionPickerWidget(context=_FakeContext())
    runtime = MainWindowStartupRuntime(widget)
    widget.startup_runtime = runtime
    widget.show()
    assert widget._recent_panel is not None
    assert widget._recent_panel._disk_verify_pending is True

    delete(widget)
    assert not isValid(widget), "the C++ object must really be gone for this test"

    # Must return silently, not raise into the event loop.
    widget._release_deferred_shelf_verify()
