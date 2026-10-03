"""Wave B — manual series overrides + internal drop targets.

Pure clustering/override behavior plus offscreen DnD routing. No
``QDrag.exec`` anywhere (synthetic ``QDropEvent``/``QDragEnterEvent`` only,
headless-safe).

Covers the frozen seam:

* override survives re-cluster (manual group keeps its id);
* ``clear_override`` returns the item to auto (re-cluster regroups);
* forced-UNGROUPED (None) is never clustered, even with an identical twin;
* internal-mime drops route to ``move_paths_to_series`` and NEVER to
  ``open_paths``/``open_folder`` (doubles, cf. ``_gallery_dispatch_doubles``).
"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QMimeData, QPoint, Qt, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QApplication, QPushButton, QWidget

from tabs.image_gallery.models import GalleryItem, Mode
from tabs.image_gallery.services.clustering import cluster_items
from tabs.image_gallery.ui import drag_drop as dnd
from tabs.image_gallery.use_cases import series_override as ov


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


# -- image fixtures ----------------------------------------------------------


def _painted(tmp_path: Path, name: str, kind: str) -> Path:
    """Two identical files per kind; kinds differ (circle vs square)."""
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


def _noise(tmp_path: Path, name: str) -> Path:
    from PIL import Image

    im = Image.effect_noise((64, 64), 64).convert("RGB")
    p = tmp_path / name
    im.save(p)
    return p


def _item(p: Path) -> GalleryItem:
    return GalleryItem(path=p, mtime_ns=p.stat().st_mtime_ns)


def _cluster(items: list[GalleryItem]):
    return cluster_items(list(items))


def _ids(items: list[GalleryItem]) -> dict[str, str | None]:
    return {it.path.name: it.series_id for it in items}


# -- pure override behavior --------------------------------------------------


def test_override_survives_recluster(tmp_path):
    a1, a2 = _item(_painted(tmp_path, "a1.png", "circle")), _item(_painted(tmp_path, "a2.png", "circle"))
    n1, n2 = _item(_noise(tmp_path, "n1.png")), _item(_noise(tmp_path, "n2.png"))
    items = [a1, a2, n1, n2]
    # Natural state: twins grouped, noise singletons.
    first = _cluster(items)
    assert a1.series_id is not None and a1.series_id == a2.series_id
    assert n1.series_id is None and n2.series_id is None

    overrides: dict = {}
    assert ov.set_override(overrides, [str(n1.path), str(n2.path)], "manual_x") == 2
    grouped = ov.apply_overrides(items, overrides, first)
    assert _ids(items)["n1.png"] == "manual_x" == _ids(items)["n2.png"]

    # Fresh re-cluster (ids may renumber) + same map → manual group keeps id.
    second = _cluster(items)
    regrouped = ov.apply_overrides(items, overrides, second)
    assert _ids(items)["n1.png"] == "manual_x" == _ids(items)["n2.png"]
    manual = [s for s in regrouped if getattr(s, "id", None) == "manual_x"]
    assert len(manual) == 1 and len(list(manual[0].members)) == 2


def test_clear_override_returns_item_to_auto(tmp_path):
    t1, t2 = _item(_painted(tmp_path, "t1.png", "circle")), _item(_painted(tmp_path, "t2.png", "circle"))
    items = [t1, t2]
    auto_id = _cluster(items)[0].id if _cluster(items) else None
    assert t1.series_id is not None and t1.series_id == t2.series_id

    overrides: dict = {}
    ov.set_override(overrides, [str(t1.path)], None)
    ov.apply_overrides(items, overrides, _cluster(items))
    assert t1.series_id is None  # forced UNGROUPED dissolves the pair

    assert ov.clear_override(overrides, [str(t1.path)]) == 1
    assert ov.get_override(overrides, str(t1.path)) is None
    regrouped = ov.apply_overrides(items, overrides, _cluster(items))
    assert t1.series_id is not None and t1.series_id == t2.series_id
    assert len(regrouped) == 1 and len(list(regrouped[0].members)) == 2
    _ = auto_id


def test_forced_ungrouped_never_clustered_with_identical_twin(tmp_path):
    t1, t2 = _item(_painted(tmp_path, "u1.png", "circle")), _item(_painted(tmp_path, "u2.png", "circle"))
    items = [t1, t2]
    _cluster(items)
    assert t1.series_id == t2.series_id is not None  # would cluster

    overrides: dict = {}
    ov.set_override(overrides, [str(t1.path)], None)
    result = ov.apply_overrides(items, overrides, _cluster(items))
    assert t1.series_id is None
    for s in result:
        members = list(getattr(s, "members", s))
        assert all(str(m.path) != str(t1.path) for m in members)


def test_override_merges_into_existing_series(tmp_path):
    t1, t2 = _item(_painted(tmp_path, "m1.png", "circle")), _item(_painted(tmp_path, "m2.png", "circle"))
    n1 = _item(_noise(tmp_path, "m3.png"))
    items = [t1, t2, n1]
    _cluster(items)
    sid = t1.series_id
    assert sid is not None and n1.series_id is None

    overrides: dict = {}
    ov.set_override(overrides, [str(n1.path)], sid)
    result = ov.apply_overrides(items, overrides, _cluster(items))
    assert n1.series_id == sid
    host = [s for s in result if getattr(s, "id", None) == sid]
    assert len(host) == 1 and len(list(host[0].members)) == 3


def test_override_dict_api_counts():
    overrides: dict = {}
    assert ov.set_override(overrides, ["a", "b"], "s1") == 2
    assert ov.get_override(overrides, "a") == "s1"
    ov.set_override(overrides, ["c"], None)
    assert "c" in overrides and ov.get_override(overrides, "c") is None
    assert ov.clear_override(overrides, ["a", "missing"]) == 1
    assert "a" not in overrides


# -- controller entry points -------------------------------------------------


def _widget_double():
    from PySide6.QtCore import QObject, Signal

    class _W(QObject):
        folder_pick_requested = Signal()
        analyze_requested = Signal(object)
        filter_text_changed = Signal(str)

    return _W()


def _controller(items: list[GalleryItem]):
    from tabs.image_gallery.controller import GalleryController

    ctrl = GalleryController(_widget_double(), context=None)
    ctrl.state.items = list(items)
    return ctrl


def test_move_paths_to_series_pins_and_retriages(tmp_path, monkeypatch):
    t1, t2 = _item(_painted(tmp_path, "c1.png", "circle")), _item(_painted(tmp_path, "c2.png", "circle"))
    ctrl = _controller([t1, t2])
    calls: dict = {}

    def _fake_triage(items, *, cover_grid=True):
        calls["items"] = list(items)
        calls["cover_grid"] = cover_grid

    monkeypatch.setattr(ctrl, "_start_triage", _fake_triage)
    moved = ctrl.move_paths_to_series([t1.path, Path("/not/in/pool.png")], "series_9")
    assert moved == 1
    assert ctrl._series_overrides == {str(t1.path): "series_9"}
    assert calls["cover_grid"] is False
    assert {str(it.path) for it in calls["items"]} == {str(t1.path), str(t2.path)}


def test_reset_series_overrides_clears_and_retriages(tmp_path, monkeypatch):
    t1 = _item(_painted(tmp_path, "r1.png", "circle"))
    ctrl = _controller([t1])
    ctrl._series_overrides = {str(t1.path): "series_9", "gone": None}
    calls: list = []
    monkeypatch.setattr(ctrl, "_start_triage", lambda items, *, cover_grid=True: calls.append(cover_grid))
    assert ctrl.reset_series_overrides() == 2
    assert ctrl._series_overrides == {}
    assert calls == [False]
    assert ctrl.reset_series_overrides() == 0  # idempotent, no rebuild
    assert calls == [False]


def test_run_triage_sync_applies_override_snapshot(tmp_path):
    t1, t2 = _item(_painted(tmp_path, "s1.png", "circle")), _item(_painted(tmp_path, "s2.png", "circle"))
    ctrl = _controller([t1, t2])
    series, _source, _mode = ctrl._run_triage_sync([t1, t2], {str(t1.path): None})
    assert t1.series_id is None
    for s in series:
        assert all(str(m.path) != str(t1.path) for m in list(getattr(s, "members", s)))


def test_on_triage_ready_reapplies_live_overrides(tmp_path, monkeypatch):
    t1, t2 = _item(_painted(tmp_path, "v1.png", "circle")), _item(_painted(tmp_path, "v2.png", "circle"))
    items = [t1, t2]
    seen: dict = {}
    widget = SimpleNamespace(
        set_triage=lambda s, m, src: seen.setdefault("series", s),
    )
    ctrl = _controller(items)
    ctrl.widget = widget
    for name in ("_start_artifact_analysis", "_start_fidelity_analysis",
                 "_start_camera_metrics_analysis", "run_tie_break_if_needed"):
        monkeypatch.setattr(ctrl, name, lambda *a, **k: None)
    computed = _cluster(items)
    assert t1.series_id == t2.series_id  # worker snapshot predates the drop
    ctrl._series_overrides = {str(t1.path): None}  # drop landed in flight
    ctrl._on_triage_ready((computed, None, Mode.CAMERA))
    assert t1.series_id is None
    delivered = seen["series"]
    for s in delivered:
        assert all(str(m.path) != str(t1.path) for m in list(getattr(s, "members", s)))


# -- internal mime parsing ---------------------------------------------------


def _internal_mime(paths: list[Path], *, with_data: bool = True, with_urls: bool = True) -> QMimeData:
    mime = QMimeData()
    if with_data:
        payload = "\n".join("file://" + str(p) for p in paths)
        mime.setData(dnd.GALLERY_PATHS_MIME, payload.encode("utf-8"))
    if with_urls:
        mime.setUrls([QUrl.fromLocalFile(str(p)) for p in paths])
    return mime


def test_gallery_paths_mime_literal():
    # Frozen seam with Wave A — identical string, never a second constant.
    assert dnd.GALLERY_PATHS_MIME == "application/x-imgsli-gallery-paths"


def test_parse_internal_paths_data_and_urls(tmp_path):
    a, b = tmp_path / "a.png", tmp_path / "b.png"
    assert [str(p) for p in dnd.parse_internal_paths(_internal_mime([a, b]))] == [str(a), str(b)]
    # Data-only (no setUrls) still parses.
    assert [str(p) for p in dnd.parse_internal_paths(_internal_mime([a], with_urls=False))] == [str(a)]
    # Urls-only (corrupt data) still resolves.
    assert [str(p) for p in dnd.parse_internal_paths(_internal_mime([b], with_data=False))] == [str(b)]
    assert dnd.parse_internal_paths(QMimeData()) == []


# -- internal drop routing (offscreen, no QDrag.exec) -------------------------


def _drop_event(mime: QMimeData) -> QDropEvent:
    ev = QDropEvent(
        QPoint(5, 5), Qt.DropAction.CopyAction, mime,
        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
    )
    ev._mime_keepalive = mime  # type: ignore[attr-defined]
    return ev


def _drag_enter_event(mime: QMimeData) -> QDragEnterEvent:
    ev = QDragEnterEvent(
        QPoint(5, 5), Qt.DropAction.CopyAction, mime,
        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
    )
    ev._mime_keepalive = mime  # type: ignore[attr-defined]
    return ev


def _recording_controller():
    calls: dict = {"move": [], "paths": [], "folders": []}
    ctrl = SimpleNamespace(
        move_paths_to_series=lambda ps, sid: calls["move"].append((list(ps), sid)),
        open_paths=lambda ps, **kw: calls["paths"].append(list(ps)),
        open_folder=lambda f: calls["folders"].append(f),
    )
    return calls, ctrl


def test_internal_drop_routes_to_move_never_open(tmp_path, qapp):
    a = tmp_path / "a.png"
    a.write_bytes(b"\x89PNG\r\n\x1a\n")
    calls, ctrl = _recording_controller()
    owner = SimpleNamespace(_series_drop_target=None, _empty_state=None)
    ev = _drop_event(_internal_mime([a]))
    dnd.drop_event(owner, ev, ctrl)
    assert ev.isAccepted()
    assert len(calls["move"]) == 1
    assert [str(p) for p in calls["move"][0][0]] == [str(a)]
    assert calls["move"][0][1] is None  # no chrome → UNGROUPED tail
    assert calls["paths"] == [] and calls["folders"] == []


def _header_host(qapp, owner_headers: bool = True):
    """Real offscreen parent acting as gallery widget + one series header."""
    owner = QWidget()
    owner.resize(400, 300)
    grid = SimpleNamespace(_series_headers=[], _series=[])
    if owner_headers:
        hdr = QWidget(owner)
        hdr.setObjectName("GallerySeriesHeader_0")
        hdr.setGeometry(0, 0, 200, 30)
        btn = QPushButton(hdr)
        btn.setObjectName("GallerySeriesHeaderBtn_0")
        btn.setGeometry(0, 0, 200, 30)
        item = SimpleNamespace(path=Path("/pool/twin.png"), series_id="series_7")
        grid._series_headers = [hdr]
        grid._series = [[item]]
    owner._grid_view = grid  # type: ignore[attr-defined]
    owner._series_drop_target = None  # type: ignore[attr-defined]
    return owner, grid


def test_internal_drop_resolves_header_series(qapp, tmp_path):
    a = tmp_path / "twin.png"
    a.write_bytes(b"\x89PNG\r\n\x1a\n")
    owner, _grid = _header_host(qapp)
    calls, ctrl = _recording_controller()
    ev = _drop_event(_internal_mime([a]))
    dnd.drop_event(owner, ev, ctrl)
    assert ev.isAccepted()
    assert len(calls["move"]) == 1
    assert calls["move"][0][1] == "series_7"
    assert calls["paths"] == [] and calls["folders"] == []


def test_internal_drop_ungrouped_header_forces_none(qapp, tmp_path):
    owner = QWidget()
    owner.resize(400, 300)
    hdr = QWidget(owner)
    hdr.setObjectName("GallerySeriesHeader_ungrouped")
    hdr.setGeometry(0, 0, 200, 30)
    owner._grid_view = SimpleNamespace(_series_headers=[hdr], _series=[])  # type: ignore[attr-defined]
    owner._series_drop_target = None  # type: ignore[attr-defined]
    a = tmp_path / "x.png"
    a.write_bytes(b"\x89PNG\r\n\x1a\n")
    calls, ctrl = _recording_controller()
    ev = _drop_event(_internal_mime([a]))
    dnd.drop_event(owner, ev, ctrl)
    assert [m[1] for m in calls["move"]] == [None]


def test_internal_drag_enter_move_highlight_header(qapp, tmp_path):
    owner, _grid = _header_host(qapp)
    a = tmp_path / "h.png"
    a.write_bytes(b"\x89PNG\r\n\x1a\n")
    mime = _internal_mime([a])
    enter = _drag_enter_event(mime)
    dnd.drag_enter_event(owner, enter)
    assert enter.isAccepted()

    from PySide6.QtGui import QDragMoveEvent

    move = QDragMoveEvent(
        QPoint(10, 10), Qt.DropAction.CopyAction, mime,
        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
    )
    move._mime_keepalive = mime  # type: ignore[attr-defined]
    dnd.drag_move_event(owner, move)
    assert move.isAccepted()
    btn = owner._grid_view._series_headers[0].findChild(QPushButton)
    assert btn is not None and btn.isDown()

    dnd.drag_leave_event(owner, None)
    assert not btn.isDown()


def test_internal_drag_enter_without_chrome_ignores(qapp, tmp_path):
    owner = QWidget()
    owner._grid_view = SimpleNamespace(_series_headers=[], _series=[])  # type: ignore[attr-defined]
    a = tmp_path / "e.png"
    a.write_bytes(b"\x89PNG\r\n\x1a\n")
    enter = _drag_enter_event(_internal_mime([a]))
    dnd.drag_enter_event(owner, enter)
    assert not enter.isAccepted()


# -- series-header reset menu ------------------------------------------------


def test_install_series_header_menu_and_reset(qapp, monkeypatch):
    owner = QWidget()
    owner.resize(400, 300)
    host = QWidget(owner)
    host.setObjectName("items_host")
    hdr = QWidget(host)
    hdr.setObjectName("GallerySeriesHeader_0")
    grid = SimpleNamespace(_series_headers=[hdr], _series=[], items_host=host)
    owner._grid_view = grid  # type: ignore[attr-defined]
    reset_calls: list = []
    ctrl = SimpleNamespace(reset_series_overrides=lambda: reset_calls.append(True))
    assert dnd.install_series_header_menu(owner, ctrl) is True
    assert dnd.install_series_header_menu(owner, ctrl) is True  # idempotent

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
            # Simulate the user picking the reset action.
            shown["triggered"](dnd._SERIES_RESET_ACTION_ID, None)

    monkeypatch.setattr("sli_ui_toolkit.widgets.ContextMenu", _FakeMenu)
    monkeypatch.setattr("sli_ui_toolkit.widgets.ContextMenuAction", _FakeAction)
    event = SimpleNamespace(
        type=lambda: QEvent.Type.ContextMenu,
        globalPosition=lambda: SimpleNamespace(toPoint=lambda: QPoint(10, 10)),
    )
    watcher = owner._series_header_watcher  # type: ignore[attr-defined]
    assert watcher.eventFilter(hdr, event) is True
    assert [a.action_id for a in shown["entries"]] == [dnd._SERIES_RESET_ACTION_ID]
    assert reset_calls == [True]


def test_header_menu_absent_without_reset_capability(qapp):
    owner = QWidget()
    hdr = QWidget(owner)
    hdr.setObjectName("GallerySeriesHeader_1")
    event = SimpleNamespace(
        type=lambda: QEvent.Type.ContextMenu,
        globalPosition=lambda: SimpleNamespace(toPoint=lambda: QPoint(1, 1)),
    )
    # Controller without reset_series_overrides → no menu, event free.
    assert dnd._open_header_reset_menu(owner, hdr, event, SimpleNamespace()) is False
