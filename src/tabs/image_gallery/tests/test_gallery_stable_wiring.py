"""Wave S2 — sync move + append-attach + Re-cluster/Reset stable wiring.

Offscreen controller/widget proofs for the frozen seam:

* move performs ZERO clustering / thread hops / analysis starts
  (override → base regroup → singleton restore → view tail);
* stable ids survive move / move-back (counter owned by the controller);
* emptied series close, 1-member leftovers keep their id + section;
* appends attach NEW files to the nearest existing series only;
* re-cluster keeps pins, reset restores auto, stale deliveries drop.
"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPoint
from PySide6.QtWidgets import QApplication, QWidget

from tabs.image_gallery.controller import GalleryController
from tabs.image_gallery.models import GalleryItem, TriageState
from tabs.image_gallery.ui import drag_drop as dnd
from tabs.image_gallery.widget import ImageGalleryWidget


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _painted(tmp_path: Path, name: str, kind: str) -> Path:
    from PIL import Image, ImageDraw

    im = Image.new("RGB", (64, 64), "white")
    d = ImageDraw.Draw(im)
    if kind == "circle":
        d.ellipse([16, 16, 48, 48], fill="red")
    else:
        d.rectangle([8, 8, 40, 40], fill="blue")
    p = tmp_path / name
    im.save(p)
    return p


def _item(p: Path) -> GalleryItem:
    return GalleryItem(path=p, mtime_ns=p.stat().st_mtime_ns)


_ANALYSIS_STARTERS = (
    "_start_artifact_analysis",
    "_start_fidelity_analysis",
    "_start_camera_metrics_analysis",
    "run_tie_break_if_needed",
)


def _seeded(qtbot, tmp_path):
    """Real widget + controller with two live series (circles / squares)."""
    w = ImageGalleryWidget()
    qtbot.addWidget(w)
    w.resize(1280, 800)
    w.show()
    items = [
        _item(_painted(tmp_path, "c1.png", "circle")),
        _item(_painted(tmp_path, "c2.png", "circle")),
        _item(_painted(tmp_path, "s1.png", "square")),
        _item(_painted(tmp_path, "s2.png", "square")),
    ]
    ctrl = GalleryController(w, context=None)
    w.attach_controller(ctrl)
    for name in _ANALYSIS_STARTERS:
        setattr(ctrl, name, lambda *a, **k: None)
    ctrl.state.items = list(items)
    w.rebuild_grid(items)
    series, source, mode = ctrl._run_triage_sync(list(items), {})
    ctrl._on_triage_ready((series, source, mode), None)
    assert len(ctrl.state.series) == 2
    c1, c2, s1, s2 = items
    assert c1.series_id == c2.series_id
    assert s1.series_id == s2.series_id
    assert c1.series_id != s1.series_id
    return ctrl, w, items


def _grid_members(w) -> list[list]:
    gv = w._grid_view
    return [list(cl) for cl in (gv._series or [])]


def test_sync_move_no_triage_no_threads_no_analysis(qtbot, tmp_path, monkeypatch):
    ctrl, w, items = _seeded(qtbot, tmp_path)
    c1, _c2, s1, _s2 = items
    sq_id = s1.series_id
    triage_calls: list = []
    pool_calls: list = []
    analysis_calls: list = []
    monkeypatch.setattr(
        ctrl, "_start_triage",
        lambda items, *, cover_grid=True: triage_calls.append(cover_grid),
    )
    ctrl._thread_pool = SimpleNamespace(start=lambda *a, **k: pool_calls.append(1))
    for name in _ANALYSIS_STARTERS:
        monkeypatch.setattr(ctrl, name, lambda *a, **k: analysis_calls.append(1))
    paint_calls: list = []
    orig_set_triage = w.set_triage

    def _rec(s, m, src):
        paint_calls.append(1)
        return orig_set_triage(s, m, src)

    monkeypatch.setattr(w, "set_triage", _rec)
    assert ctrl.move_paths_to_series([c1.path], sq_id) == 1
    assert triage_calls == []  # zero triage starts
    assert pool_calls == []  # zero thread hops
    assert analysis_calls == []  # zero analysis starts
    assert c1.series_id == sq_id
    # Grid shows the card in the target series (3 members, no UNGROUPED).
    host = [cl for cl in _grid_members(w) if any(m.path == c1.path for m in cl)]
    assert len(host) == 1 and len(host[0]) == 3
    assert list(w._grid_view._ungrouped or []) == []
    # Second identical move is a no-op with no repaint.
    assert ctrl.move_paths_to_series([c1.path], sq_id) == 0
    assert len(paint_calls) == 1


def test_stable_ids_across_move_and_move_back(qtbot, tmp_path):
    ctrl, _w, items = _seeded(qtbot, tmp_path)
    c1, _c2, s1, _s2 = items
    circ_id, sq_id = c1.series_id, s1.series_id
    before = {it.path.name: it.series_id for it in items}
    assert ctrl._series_next_id == 3  # seed consumed series_1/series_2
    assert ctrl.move_paths_to_series([c1.path], sq_id) == 1
    # Target ids verbatim; leftover keeps its id; counter untouched.
    assert {m.series_id for m in items if m.path.name.startswith("s")} == {sq_id}
    assert ctrl._series_next_id == 3
    leftover = [s for s in ctrl.state.series if getattr(s, "id", None) == circ_id]
    assert len(leftover) == 1
    assert ctrl.move_paths_to_series([c1.path], circ_id) == 1
    assert {it.path.name: it.series_id for it in items} == before


def test_emptied_series_closes(qtbot, tmp_path):
    ctrl, _w, items = _seeded(qtbot, tmp_path)
    c1, c2, s1, _s2 = items
    circ_id, sq_id = c1.series_id, s1.series_id
    assert ctrl.move_paths_to_series([c1.path], sq_id) == 1
    assert ctrl.move_paths_to_series([c2.path], sq_id) == 1
    ids = [getattr(s, "id", None) for s in ctrl.state.series]
    assert circ_id not in ids  # 0-member series renders nothing
    host = [s for s in ctrl.state.series if getattr(s, "id", None) == sq_id]
    assert len(host) == 1 and len(list(host[0].members)) == 4


def test_singleton_leftover_keeps_id_and_section(qtbot, tmp_path):
    ctrl, w, items = _seeded(qtbot, tmp_path)
    c1, c2, s1, _s2 = items
    circ_id = c1.series_id
    assert ctrl.move_paths_to_series([c1.path], s1.series_id) == 1
    single = [s for s in ctrl.state.series if getattr(s, "id", None) == circ_id]
    assert len(single) == 1
    assert [m.path for m in list(single[0].members)] == [c2.path]
    assert c2.series_id == circ_id and c2.rank == 1
    # Painted as its own SERIES section (not the UNGROUPED tail).
    gv = w._grid_view
    assert any(len(cl) == 1 for cl in _grid_members(w))
    headers = list(gv._series_headers or [])
    assert len(headers) == 2
    assert all("ungrouped" not in str(h.objectName() or "") for h in headers)
    card = gv.card_for(c2.path)
    assert card is not None and card.isVisible()


def test_append_attach_leaves_existing_alone(qtbot, tmp_path, monkeypatch):
    ctrl, w, items = _seeded(qtbot, tmp_path)
    c1, c2, s1, s2 = items
    circ_id, sq_id = c1.series_id, s1.series_id
    snapshot = {
        str(it.path): (it.series_id, it.rank) for it in items
    }
    triage_calls: list = []
    monkeypatch.setattr(
        ctrl, "_start_triage",
        lambda items, *, cover_grid=True: triage_calls.append(cover_grid),
    )
    monkeypatch.setattr(ctrl, "_load_thumbnail", lambda item: None)
    c3 = tmp_path / "c3.png"
    _painted(tmp_path, "c3.png", "circle")
    ctrl.open_paths([c3])
    assert triage_calls == []  # attach-only: no retriage over the live pool
    assert ctrl.state.triage_state == TriageState.DONE
    by_path = {str(it.path): it for it in ctrl.state.items}
    assert by_path[str(c3)].series_id == circ_id  # nearest existing series
    for it in items:  # existing membership untouched
        assert (it.series_id, it.rank) == snapshot[str(it.path)]
    assert c1.series_id == c2.series_id == circ_id != sq_id
    assert s1.series_id == s2.series_id == sq_id
    assert ctrl.state.mode is not None
    host = [cl for cl in _grid_members(w) if any(m.path.name == "c3.png" for m in cl)]
    assert len(host) == 1 and len(host[0]) == 3


def test_recluster_keeps_pins(qtbot, tmp_path, monkeypatch):
    ctrl, _w, items = _seeded(qtbot, tmp_path)
    c1, _c2, s1, _s2 = items
    sq_id = s1.series_id
    assert ctrl.move_paths_to_series([c1.path], sq_id) == 1
    triage_calls: list = []
    monkeypatch.setattr(
        ctrl, "_start_triage",
        lambda items, *, cover_grid=True: triage_calls.append((list(items), cover_grid)),
    )
    ctrl.recluster_series()
    assert len(triage_calls) == 1
    assert triage_calls[0][1] is False
    assert {str(it.path) for it in triage_calls[0][0]} == {str(it.path) for it in items}
    # Manual delivery of the fresh world: the pin survives.
    series, source, mode = ctrl._run_triage_sync(
        list(ctrl.state.items), dict(ctrl._series_overrides)
    )
    ctrl._on_triage_ready((series, source, mode), None)
    assert c1.series_id == sq_id
    host = [s for s in ctrl.state.series if getattr(s, "id", None) == sq_id]
    assert len(host) == 1 and any(m.path == c1.path for m in list(host[0].members))


def test_reset_restores_auto(qtbot, tmp_path, monkeypatch):
    ctrl, _w, items = _seeded(qtbot, tmp_path)
    c1, c2, s1, _s2 = items
    assert ctrl.move_paths_to_series([c1.path], s1.series_id) == 1
    triage_calls: list = []
    monkeypatch.setattr(
        ctrl, "_start_triage",
        lambda items, *, cover_grid=True: triage_calls.append(cover_grid),
    )
    assert ctrl.reset_series_overrides() == 1
    assert ctrl._series_overrides == {}
    assert triage_calls == [False]
    series, source, mode = ctrl._run_triage_sync(list(ctrl.state.items), {})
    ctrl._on_triage_ready((series, source, mode), None)
    assert c1.series_id is not None and c1.series_id == c2.series_id
    assert c1.series_id != s1.series_id


def test_stale_triage_delivery_drops_after_sync_move(qtbot, tmp_path):
    ctrl, _w, items = _seeded(qtbot, tmp_path)
    c1, _c2, s1, _s2 = items
    sq_id = s1.series_id
    # A worker started BEFORE the move delivers after it: dropped.
    stale, _src, _mode = ctrl._run_triage_sync(list(items), {})
    assert ctrl.move_paths_to_series([c1.path], sq_id) == 1
    ctrl._on_triage_ready((stale, None, None), None, 0)
    assert c1.series_id == sq_id
    host = [s for s in ctrl.state.series if getattr(s, "id", None) == sq_id]
    assert len(host) == 1 and any(m.path == c1.path for m in list(host[0].members))


def _fake_menu(monkeypatch):
    shown: dict = {}

    class _FakeAction:
        def __init__(self, action_id, label, **kw):
            self.action_id = action_id

    class _FakeMenu:
        def __init__(self, source, entries=(), on_triggered=None, **kw):
            shown["entries"] = list(entries)
            shown["triggered"] = on_triggered

        def popup_at(self, pos):
            shown["pos"] = pos

    monkeypatch.setattr("sli_ui_toolkit.widgets.ContextMenu", _FakeMenu)
    monkeypatch.setattr("sli_ui_toolkit.widgets.ContextMenuAction", _FakeAction)
    return shown


def test_header_menu_offers_reset_and_recluster(qapp, monkeypatch):
    owner = QWidget()
    owner.resize(400, 300)
    hdr = QWidget(owner)
    hdr.setObjectName("GallerySeriesHeader_0")
    calls: list = []
    ctrl = SimpleNamespace(
        reset_series_overrides=lambda: calls.append("reset"),
        recluster_series=lambda: calls.append("recluster"),
    )
    shown = _fake_menu(monkeypatch)
    event = SimpleNamespace(
        type=lambda: QEvent.Type.ContextMenu,
        globalPosition=lambda: SimpleNamespace(toPoint=lambda: QPoint(10, 10)),
    )
    assert dnd._open_header_reset_menu(owner, hdr, event, ctrl) is True
    assert [a.action_id for a in shown["entries"]] == [
        dnd._SERIES_RESET_ACTION_ID,
        dnd._SERIES_RECLUSTER_ACTION_ID,
    ]
    shown["triggered"](dnd._SERIES_RECLUSTER_ACTION_ID, None)
    shown["triggered"](dnd._SERIES_RESET_ACTION_ID, None)
    assert calls == ["recluster", "reset"]


def test_header_menu_recluster_only(qapp, monkeypatch):
    owner = QWidget()
    hdr = QWidget(owner)
    hdr.setObjectName("GallerySeriesHeader_1")
    calls: list = []
    ctrl = SimpleNamespace(recluster_series=lambda: calls.append(True))
    shown = _fake_menu(monkeypatch)
    event = SimpleNamespace(
        type=lambda: QEvent.Type.ContextMenu,
        globalPosition=lambda: SimpleNamespace(toPoint=lambda: QPoint(1, 1)),
    )
    assert dnd._open_header_reset_menu(owner, hdr, event, ctrl) is True
    assert [a.action_id for a in shown["entries"]] == [dnd._SERIES_RECLUSTER_ACTION_ID]
    shown["triggered"](dnd._SERIES_RECLUSTER_ACTION_ID, None)
    assert calls == [True]
