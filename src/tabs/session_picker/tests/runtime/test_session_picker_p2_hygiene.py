"""Session-picker P2 hygiene bundle (task-fix-session-picker-p2-2026-09-20).

Covers:
* nested drag enter/leave discipline (depth counter — no flicker/freeze
  across the panel's installed child widgets) + drop resets the depth.
* empty-path drops report via ``on_empty_drop`` instead of silent consume;
  non-empty drops still defer through ``on_paths``.
* dead ``_PANEL_MARGIN_*`` consts are gone from ``panel.py``.
* dead ``SessionPickerWidget._clear_cards`` is gone (in-place retranslate
  stays the only card-text path — no CSD-hole rebuild).
* content-width floor is design px applied via de-scaled resolve
  (identity at factor 1.0, device-space floor at 1.5).
* ``activate()`` resolves a live missing flag when none is given (no
  hardcoded False); explicit flags keep their refresh semantics.

Headless-safe: ``qapp`` only for QWidget hosts. ``items_view.py`` is a
read-only reference here — its keyboard/scroll suite must stay green
(verified by running it alongside).
"""

from __future__ import annotations

import ast
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QWidget


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _controller(host, *, on_paths=None, on_empty=None):
    from tabs.session_picker.recent.drop_controller import RecentDropController

    changed: list = []
    return (
        RecentDropController(
            host,
            on_paths=on_paths or (lambda ps: None),
            on_active_changed=changed.append,
            on_empty_drop=on_empty,
        ),
        changed,
    )


def _drag_event(*, accepted: bool = True):
    calls: dict = {"accept": 0, "ignore": 0, "propose": 0}
    return (
        SimpleNamespace(
            source=lambda: None,
            mimeData=lambda: SimpleNamespace(hasUrls=lambda: True, urls=lambda: []),
            acceptProposedAction=lambda: calls.__setitem__("propose", 1),
            accept=lambda: (calls.__setitem__("accept", 1), True)[1],
            ignore=lambda: calls.__setitem__("ignore", 1),
            isAccepted=lambda: bool(calls["accept"]),
        ),
        calls,
    )


# --------------------------------------------------------------------------
# nested enter/leave discipline
# --------------------------------------------------------------------------


def test_nested_enter_leave_keeps_highlight(qapp, monkeypatch):
    import tabs.session_picker.recent.drop_controller as dc

    monkeypatch.setattr(dc, "mime_has_external_project", lambda event: True)
    host = QWidget()
    ctrl, changed = _controller(host)
    enter, _ = _drag_event()
    leave, _ = _drag_event()

    ctrl.handle_drag_enter(enter)  # panel
    ctrl.handle_drag_enter(enter)  # child boundary
    assert ctrl.drag_active is True
    ctrl.handle_drag_leave(leave)  # back to panel — still inside
    assert ctrl.drag_active is True
    assert changed == [True]  # no flicker off/on
    ctrl.handle_drag_leave(leave)  # left the shelf
    assert ctrl.drag_active is False
    assert changed == [True, False]
    host.deleteLater()


def test_drop_resets_depth(qapp, monkeypatch):
    import tabs.session_picker.recent.drop_controller as dc

    monkeypatch.setattr(dc, "mime_has_external_project", lambda event: True)
    monkeypatch.setattr(dc, "project_paths_from_mime", lambda mime: ["/x/a.imgsli"])
    host = QWidget()
    pinned: list = []
    ctrl, changed = _controller(host, on_paths=pinned.append)
    enter, _ = _drag_event()
    drop, _ = _drag_event()

    ctrl.handle_drag_enter(enter)
    ctrl.handle_drag_enter(enter)
    fired: list = []
    monkeypatch.setattr(
        "PySide6.QtCore.QTimer.singleShot", lambda ms, fn: fired.append(fn)
    )
    ctrl.handle_drop(drop)
    assert ctrl.drag_active is False
    assert ctrl._drag_depth == 0
    assert len(fired) == 1
    fired[0]()
    assert pinned == [["/x/a.imgsli"]]
    host.deleteLater()


def test_empty_drop_reports_not_silent(qapp, monkeypatch):
    import tabs.session_picker.recent.drop_controller as dc

    monkeypatch.setattr(dc, "mime_has_external_project", lambda event: True)
    monkeypatch.setattr(dc, "project_paths_from_mime", lambda mime: [])
    host = QWidget()
    pinned: list = []
    emptied: list = []
    ctrl, _changed = _controller(
        host, on_paths=pinned.append, on_empty=lambda: emptied.append(1)
    )
    drop, calls = _drag_event()
    ctrl.handle_drop(drop)
    # Consumed (accepted) but reported — never silently swallowed.
    assert calls["accept"] == 1
    assert pinned == []
    assert emptied == [1]
    host.deleteLater()


# --------------------------------------------------------------------------
# dead code removal guards
# --------------------------------------------------------------------------


def test_panel_has_no_dead_margin_consts():
    path = Path(__file__).resolve().parents[2] / "recent" / "panel.py"
    tree = ast.parse(path.read_text())
    defined = {
        n.targets[0].id
        for n in ast.walk(tree)
        if isinstance(n, ast.Assign)
        and len(n.targets) == 1
        and isinstance(n.targets[0], ast.Name)
    }
    for banned in (
        "_PANEL_MARGIN_LEFT",
        "_PANEL_MARGIN_TOP",
        "_PANEL_MARGIN_RIGHT",
        "_PANEL_MARGIN_BOTTOM",
        "_PANEL_SPACING",
    ):
        assert banned not in defined


def test_widget_has_no_dead_clear_cards():
    path = Path(__file__).resolve().parents[2] / "widget.py"
    tree = ast.parse(path.read_text())
    methods = {
        n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
    }
    assert "_clear_cards" not in methods


# --------------------------------------------------------------------------
# design-px floor via de-scaled resolve
# --------------------------------------------------------------------------


def test_descale_px_unit():
    from sli_ui_toolkit.managers import UiScale

    from tabs.session_picker.recent.use_cases.sizing import _descale_px

    UiScale.get_instance().set_factor(1.5)
    try:
        assert _descale_px(696) == 464
        assert _descale_px(0) == 0
    finally:
        UiScale.get_instance().set_factor(1.0)
    assert _descale_px(592) == 592


def test_grid_content_width_floor_holds_in_device_space(qapp):
    from sli_ui_toolkit.managers import UiScale

    from tabs.session_picker.geometry import (
        SESSION_PICKER_RECENT_CONTENT_WIDTH_FLOOR,
    )
    from tabs.session_picker.recent.panel import RecentProjectsPanel
    from tabs.session_picker.recent.use_cases import sizing

    UiScale.get_instance().set_factor(1.5)
    try:
        panel = RecentProjectsPanel(translate=lambda k, d="", **kw: d or k)
        try:
            width = sizing.grid_content_width(panel)
        finally:
            panel.deleteLater()
    finally:
        UiScale.get_instance().set_factor(1.0)
    # Floor bites in device px (696), not raw design px (464).
    from sli_ui_toolkit.managers import scaled_px

    assert width >= scaled_px(SESSION_PICKER_RECENT_CONTENT_WIDTH_FLOOR)
    assert width >= 696


# --------------------------------------------------------------------------
# live missing flag
# --------------------------------------------------------------------------


def _record(path: str):
    from services.io.recent_projects import RecentProjectRecord

    return RecentProjectRecord(
        path=path,
        display_name=Path(path).name,
        opened_at="2026-01-01T00:00:00+00:00",
        session_types=("image_compare",),
    )


def _panel_fake():
    opened: list = []
    refreshed: list = []
    return (
        SimpleNamespace(
            _on_open=lambda p: opened.append(p),
            refresh=lambda: refreshed.append(1),
        ),
        opened,
        refreshed,
    )


def test_activate_live_opens_existing(tmp_path):
    from tabs.session_picker.recent.use_cases import selection_ops

    proj = tmp_path / "alive.imgsli"
    proj.write_text("{}")
    panel, opened, refreshed = _panel_fake()
    selection_ops.activate(panel, _record(str(proj)))
    assert opened == [str(proj)]
    assert refreshed == []


def test_activate_live_blocks_missing(tmp_path):
    from tabs.session_picker.recent.use_cases import selection_ops

    panel, opened, refreshed = _panel_fake()
    selection_ops.activate(panel, _record(str(tmp_path / "gone.imgsli")))
    assert opened == []
    assert refreshed == []


def test_activate_explicit_stale_flag_still_refreshes(tmp_path):
    from tabs.session_picker.recent.use_cases import selection_ops

    proj = tmp_path / "vanished.imgsli"
    proj.write_text("{}")
    panel, opened, refreshed = _panel_fake()
    proj.unlink()
    selection_ops.activate(panel, _record(str(proj)), missing=False)
    assert opened == []
    assert refreshed == [1]
