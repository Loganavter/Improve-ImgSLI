"""First paint of the recent shelf must not stat the disk.

Measured (cold-start recon, 2026-10-24): the session-picker page refreshed the
recent list *before* the first visible paint and fingerprinted every record with
``os.stat`` -- up to ``DEFAULT_CAP`` = 1000 paths. That is 2.8 ms per 1000 on a
local disk but seconds on a network/shared path, which is exactly the WinBoat
host's situation.

Contract: the first pass renders stored records and schedules ONE verification
pass after the paint; the deferred pass does the stats and rebuilds only if the
live state differs.
"""

from __future__ import annotations

from types import SimpleNamespace

from tabs.session_picker.recent.use_cases import refresh as refresh_uc


class _Items:
    def apply_selection(self) -> None:
        pass


class _Panel:
    def __init__(self) -> None:
        self._view_mode = "list"
        self._sort_mode = "recent"
        self._sort_order = "desc"
        self._records = [SimpleNamespace(path="/a", opened_at=1, display_name="a", session_types=[])]
        self._selected_paths: set = set()
        self._disk_snapshot = "unset"
        self._layout_ready = False
        self._items = _Items()
        self.rebuilds = 0

    def _rebuild_items(self) -> None:
        self.rebuilds += 1

    def _sync_header_controls(self) -> None:
        pass

    def _sync_opaque_fills(self) -> None:
        pass


def _patch_panel_module(monkeypatch):
    import tabs.session_picker.recent.panel as panel_mod

    monkeypatch.setattr(panel_mod, "get_recent_view_mode", lambda: "list", raising=False)
    monkeypatch.setattr(panel_mod, "get_recent_sort_mode", lambda: "recent", raising=False)
    monkeypatch.setattr(panel_mod, "get_recent_sort_order", lambda: "desc", raising=False)
    monkeypatch.setattr(
        panel_mod,
        "list_recent_projects",
        lambda drop_missing=False: [SimpleNamespace(path="/a", opened_at=1, display_name="a", session_types=[])],
        raising=False,
    )
    monkeypatch.setattr(panel_mod, "sort_recent_projects", lambda records, **kw: list(records), raising=False)


def test_first_paint_does_not_stat_and_schedules_one_pass(monkeypatch):
    _patch_panel_module(monkeypatch)
    stat_calls: list[str] = []
    scheduled: list[object] = []

    monkeypatch.setattr(
        refresh_uc, "_disk_fingerprint", lambda path: stat_calls.append(path) or (True, 1)
    )
    monkeypatch.setattr(refresh_uc, "_schedule_disk_verify", lambda panel: scheduled.append(panel))

    panel = _Panel()
    refresh_uc.refresh(panel, verify_disk=False)

    assert stat_calls == [], "the first pass stat'ed the disk (network-path freeze)"
    assert scheduled == [panel], "the first pass must schedule exactly one verification pass"
    assert panel._disk_snapshot is None, "unverified state must not claim a snapshot"
    assert panel.rebuilds == 1, "records still need to be rendered on the first pass"


def test_deferred_pass_stats_once_then_rebuilds_only_on_change(monkeypatch):
    _patch_panel_module(monkeypatch)
    panel = _Panel()
    panel._disk_snapshot = None

    live = [("/a", True, 1)]
    monkeypatch.setattr(refresh_uc, "_live_state", lambda records: live)

    # First deferred pass: the shelf was rendered unverified, so recording what
    # the disk actually looks like must repaint once.
    refresh_uc.verify_disk_now(panel)
    assert panel._disk_snapshot == live, "the deferred pass must record what it saw"
    assert panel.rebuilds == 1, "first verification must repaint the shelf once"

    # Same live state again: nothing to do (no repaint, no churn).
    refresh_uc.verify_disk_now(panel)
    assert panel.rebuilds == 1, "an unchanged disk must not rebuild the shelf"

    # External delete: the state differs, so repaint.
    changed = [("/a", False, None)]
    monkeypatch.setattr(refresh_uc, "_live_state", lambda records: changed)
    refresh_uc.verify_disk_now(panel)
    assert panel._disk_snapshot == changed
    assert panel.rebuilds == 2, "an external delete/edit must rebuild the shelf"
