"""UIUpdateBatcher liveness guard routes via TabContract capability (Wave W-A).

The flush guard used to ``importlib.import_module`` a concrete tab's
``live_handles``. It now resolves the ``qt_liveness_probe`` capability
once (cached — this path is HOT) and falls back to a host-local shiboken
check with identical verdicts when no tab provides it.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication, QWidget

import tabs.registry as tabs_registry
from ui.presenters import ui_update_batcher as batcher_module
from ui.presenters.ui_update_batcher import UIUpdateBatcher


@pytest.fixture
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def _fresh_probe_cache(monkeypatch):
    """Reset the cached capability resolution around each test."""
    monkeypatch.setattr(batcher_module, "_cached_liveness_probe", batcher_module._UNRESOLVED)


def _qt_presenter(**methods):
    presenter = QWidget()
    presenter.main_window_app = None
    for name, fn in methods.items():
        setattr(presenter, name, fn)
    return presenter


class _FakeRegistry:
    """Stand-in for the shared tab registry (capability probe counter)."""

    def __init__(self, probe=None, raises=False):
        self.probe = probe
        self.raises = raises
        self.calls: list[str] = []

    def create_startup_service(self, service_id, *args, **kwargs):
        self.calls.append(service_id)
        if self.raises:
            raise RuntimeError("registry broken")
        return self.probe


def _install_registry(monkeypatch, fake):
    monkeypatch.setattr(tabs_registry, "get_shared_tab_registry", lambda: fake)


def test_source_proof_no_dynamic_tab_import():
    """The batcher must not name a concrete tab (frozen contract)."""
    import pathlib

    source = pathlib.Path(batcher_module.__file__).read_text()
    assert "import_module" not in source
    assert "importlib" not in source
    assert "live_handles" not in source
    for literal in ("image_compare", "multi_compare", "session_picker", "image_gallery"):
        assert literal not in source, f"session_type literal {literal!r} in host batcher"


def test_local_fallback_matches_tab_probe_verdicts(qapp):
    """Host-local check gives the same liveness as the old tab-owned probe.

    The old path called the tab's ``is_qt_alive``, which is exactly
    ``shiboken6.isValid`` fail-open True — compare against raw shiboken
    directly so this host test never imports tab internals itself.
    """
    import shiboken6
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QPushButton

    parent = QWidget()
    live = QPushButton(parent)
    dead = QPushButton(parent)
    dead.deleteLater()  # C++ gone, Python wrapper alive
    QTest.qWait(50)
    try:
        assert batcher_module._is_qt_alive_local(live) == bool(shiboken6.isValid(live)) == True
        assert batcher_module._is_qt_alive_local(dead) == bool(shiboken6.isValid(dead)) == False
        assert batcher_module._is_qt_alive_local(object()) == True
    finally:
        parent.deleteLater()


def test_capability_probe_drives_guard_and_resolves_once(qapp, monkeypatch):
    """Mock providing tab: dead per probe vetoes the flush; looked up once."""
    seen: list[object] = []

    def _probe(obj):
        seen.append(obj)
        return False

    fake = _FakeRegistry(probe=_probe)
    _install_registry(monkeypatch, fake)
    calls: list[str] = []
    presenter = _qt_presenter(_do_update_combobox_displays=lambda: calls.append("combobox"))
    try:
        batcher = UIUpdateBatcher(presenter)
        batcher._pending_updates = {"combobox"}
        batcher._flush_updates()
        # Probe said dead → early return, branch never ran.
        assert calls == []
        assert seen == [presenter]
        assert fake.calls == [batcher_module._LIVENESS_CAPABILITY_ID]

        # Second flush reuses the cached probe — no per-frame registry scan.
        batcher._pending_updates = {"combobox"}
        batcher._flush_updates()
        assert fake.calls == [batcher_module._LIVENESS_CAPABILITY_ID]
    finally:
        presenter.deleteLater()


def test_capability_probe_alive_runs_branches(qapp, monkeypatch):
    """Mock providing tab: alive per probe lets the flush through."""
    fake = _FakeRegistry(probe=lambda obj: True)
    _install_registry(monkeypatch, fake)
    calls: list[str] = []
    presenter = _qt_presenter(_do_update_combobox_displays=lambda: calls.append("combobox"))
    try:
        batcher = UIUpdateBatcher(presenter)
        batcher._pending_updates = {"combobox"}
        batcher._flush_updates()
        assert calls == ["combobox"]
    finally:
        presenter.deleteLater()


@pytest.mark.parametrize("raises", [False, True])
def test_absent_or_broken_registry_fail_open(qapp, monkeypatch, raises):
    """No provider (None) or a raising registry: flush proceeds, never raises."""
    fake = _FakeRegistry(probe=None, raises=raises)
    _install_registry(monkeypatch, fake)
    calls: list[str] = []
    presenter = _qt_presenter(_do_update_combobox_displays=lambda: calls.append("combobox"))
    try:
        batcher = UIUpdateBatcher(presenter)
        batcher._pending_updates = {"combobox"}
        batcher._flush_updates()  # must not raise
        assert calls == ["combobox"]
    finally:
        presenter.deleteLater()
