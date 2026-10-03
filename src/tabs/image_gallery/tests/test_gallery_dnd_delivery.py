"""Wave C — DnD delivery fixes (truthful intra-gallery delivery + strip router).

Offscreen-safe throughout: no ``QDrag.exec``, synthetic events only,
real QWidget geometry for hit-testing, doubles for controller/store/
registry. Covers:

* C1 no-op guard: pre-pinned targets → ``move_paths_to_series`` returns 0
  WITHOUT ``_start_triage`` (no pointless rebuild / Stage-2 re-analysis);
  partial overlap proceeds for the rest only, single retriage.
* C1 owner-space mapping: a fake event whose receiver-relative pos would
  MISS but whose global pos sits over a known header resolves that header's
  series (the S2 receiver != owner bug); the success path logs the delivery.
* C2 strip router: unknown session / declining tab / own-gallery tab →
  ignored; accepting tab → session switch + pending-insert scheduled.
"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QMimeData, QPoint, QPointF, QRect, Qt, QUrl
from PySide6.QtWidgets import QApplication, QWidget

from tabs.image_gallery.models import GalleryItem
from tabs.image_gallery.ui import drag_drop as dnd


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _item(p: Path, series_id=None) -> GalleryItem:
    it = GalleryItem(path=p, mtime_ns=0)
    it.series_id = series_id
    return it


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


# -- C1: no-op guard ---------------------------------------------------------


def test_move_noop_when_all_targets_already_pinned(tmp_path, monkeypatch):
    a = tmp_path / "a.png"
    a.write_bytes(b"\x89PNG\r\n\x1a\n")
    b = tmp_path / "b.png"
    b.write_bytes(b"\x89PNG\r\n\x1a\n")
    ctrl = _controller([_item(a, "series_7"), _item(b, "series_7")])
    triage_calls: list = []
    monkeypatch.setattr(
        ctrl, "_start_triage",
        lambda items, *, cover_grid=True: triage_calls.append((list(items), cover_grid)),
    )
    assert ctrl.move_paths_to_series([a, b], "series_7") == 0
    assert triage_calls == []  # no rebuild, no re-analysis
    assert ctrl._series_overrides == {}


def test_move_noop_ungrouped_targets_to_none(tmp_path, monkeypatch):
    a = tmp_path / "u.png"
    a.write_bytes(b"\x89PNG\r\n\x1a\n")
    ctrl = _controller([_item(a, None)])
    triage_calls: list = []
    monkeypatch.setattr(
        ctrl, "_start_triage",
        lambda items, *, cover_grid=True: triage_calls.append(True),
    )
    assert ctrl.move_paths_to_series([a], None) == 0
    assert triage_calls == []


def test_move_partial_overlap_proceeds_for_rest_once(tmp_path, monkeypatch):
    a = tmp_path / "p1.png"
    a.write_bytes(b"\x89PNG\r\n\x1a\n")
    b = tmp_path / "p2.png"
    b.write_bytes(b"\x89PNG\r\n\x1a\n")
    ctrl = _controller([_item(a, "series_7"), _item(b, None)])
    triage_calls: list = []
    monkeypatch.setattr(
        ctrl, "_start_triage",
        lambda items, *, cover_grid=True: triage_calls.append(cover_grid),
    )
    assert ctrl.move_paths_to_series([a, b], "series_7") == 1
    assert ctrl._series_overrides == {str(b): "series_7"}  # a untouched
    assert triage_calls == [False]  # still exactly one retriage


def test_move_full_change_still_retriages(tmp_path, monkeypatch):
    a = tmp_path / "f.png"
    a.write_bytes(b"\x89PNG\r\n\x1a\n")
    ctrl = _controller([_item(a, None)])
    triage_calls: list = []
    monkeypatch.setattr(
        ctrl, "_start_triage",
        lambda items, *, cover_grid=True: triage_calls.append(cover_grid),
    )
    assert ctrl.move_paths_to_series([a], "series_9") == 1
    assert triage_calls == [False]


# -- C1: owner-space mapping + delivery logging ------------------------------


class _FakeDropEvent:
    """Synthetic internal drop: receiver-relative pos MISSES, global HITS.

    Proves the Wave C fix — ``_owner_space_pos`` maps the global cursor into
    owner space instead of trusting the receiver-relative pos (S2: receiver
    ``!=`` owner, e.g. viewport/zone child).
    """

    def __init__(self, mime: QMimeData, global_pos: QPoint):
        self._mime = mime
        self._global = global_pos
        self.accepted = False
        self.ignored = False

    def mimeData(self):
        return self._mime

    def globalPosition(self):
        return QPointF(self._global)

    def position(self):  # receiver-relative decoy: far from every header
        return QPointF(QPoint(500, 500))

    def pos(self):
        return QPoint(500, 500)

    def accept(self):
        self.accepted = True

    def ignore(self):
        self.ignored = True

    def acceptProposedAction(self):
        self.accepted = True


def _internal_mime(paths: list[Path]) -> QMimeData:
    mime = QMimeData()
    mime.setData(
        dnd.GALLERY_PATHS_MIME,
        ("\n".join("file://" + str(p) for p in paths)).encode("utf-8"),
    )
    mime.setUrls([QUrl.fromLocalFile(str(p)) for p in paths])
    return mime


def _owner_with_header(qapp, series_id: str):
    owner = QWidget()
    owner.resize(400, 300)
    hdr = QWidget(owner)
    hdr.setObjectName("GallerySeriesHeader_0")
    hdr.setGeometry(0, 0, 200, 30)
    item = SimpleNamespace(path=Path("/pool/twin.png"), series_id=series_id)
    owner._grid_view = SimpleNamespace(  # type: ignore[attr-defined]
        _series_headers=[hdr], _series=[[item]]
    )
    owner._series_drop_target = None  # type: ignore[attr-defined]
    return owner, hdr


def test_owner_space_pos_prefers_global_over_receiver_pos(qapp, tmp_path):
    owner, hdr = _owner_with_header(qapp, "series_7")
    a = tmp_path / "twin.png"
    a.write_bytes(b"\x89PNG\r\n\x1a\n")
    # Global point over the header (round-trips through mapToGlobal).
    gp = hdr.mapToGlobal(QPoint(10, 10))
    ev = _FakeDropEvent(_internal_mime([a]), gp)
    assert dnd._owner_space_pos(owner, ev) == QPoint(10, 10)
    handled, sid = dnd.series_target_at(owner, dnd._owner_space_pos(owner, ev))
    assert (handled, sid) == (True, "series_7")


def test_internal_drop_logs_resolved_delivery(qapp, tmp_path, monkeypatch, caplog):
    monkeypatch.setenv("IMGSLI_GALLERY_DEBUG", "1")
    owner, hdr = _owner_with_header(qapp, "series_7")
    a = tmp_path / "twin.png"
    a.write_bytes(b"\x89PNG\r\n\x1a\n")
    calls: list = []
    ctrl = SimpleNamespace(
        move_paths_to_series=lambda ps, sid: calls.append((list(ps), sid)) or 2,
    )
    ev = _FakeDropEvent(_internal_mime([a]), hdr.mapToGlobal(QPoint(10, 10)))
    with caplog.at_level("WARNING", logger="ImproveImgSLI"):
        dnd.drop_event(owner, ev, ctrl)
    assert ev.accepted
    assert len(calls) == 1 and calls[0][1] == "series_7"
    delivered = [r for r in caplog.records if "internal drop delivered" in r.getMessage()]
    assert len(delivered) == 1
    msg = delivered[0].getMessage()
    assert "series_7" in msg and "moved=2" in msg


# -- C2: strip router --------------------------------------------------------


def test_card_mime_mirror_matches_single_definition():
    """Platform router/strip share ONE wire string with the tab-side mime.

    The host sandbox forbids ``src/ui`` importing the tab-side constant, so
    ``ui.main_window.tab_strip_drop.GALLERY_CARD_MIME`` is a mirror — this
    pins it equal to the single definition (Wave A frozen seam). If this
    fails, update the mirror, never add a third copy.
    """
    from tabs.image_gallery.ui.card import GALLERY_PATHS_MIME
    from ui.main_window.tab_strip_drop import GALLERY_CARD_MIME

    assert GALLERY_CARD_MIME == GALLERY_PATHS_MIME == "application/x-imgsli-gallery-paths"


class _FakeBar:
    """Two tabs: [0,150) → tab 0, [150,300) → tab 1; origin at (1000, 40)."""

    _ORIGIN = QPoint(1000, 40)

    def mapFromGlobal(self, gp: QPoint) -> QPoint:
        return gp - self._ORIGIN

    def rect(self) -> QRect:
        return QRect(0, 0, 300, 30)

    def tabAt(self, pos: QPoint) -> int:
        if QRect(0, 0, 150, 30).contains(pos):
            return 0
        if QRect(150, 0, 150, 30).contains(pos):
            return 1
        return -1


class _FakeStrip:
    def __init__(self):
        self.tab_bar = _FakeBar()
        self._data = {0: "sess-a", 1: "sess-b"}
        self.current: int | None = None

    def tabData(self, index: int):
        return self._data.get(index)

    def setCurrentIndex(self, index: int):
        self.current = index


class _FakeStore:
    def __init__(self, sessions: dict, active_id: str | None):
        self._sessions = sessions
        self.workspace = SimpleNamespace(active_session_id=active_id)
        self.switched: list = []

    def get_workspace_session(self, session_id):
        return self._sessions.get(session_id)

    def switch_workspace_session(self, session_id):
        self.switched.append(session_id)
        return True


def _session(session_id: str, session_type: str):
    return SimpleNamespace(id=session_id, session_type=session_type)


def _tab_pos(tab_index: int) -> QPoint:
    return _FakeBar._ORIGIN + QPoint(75 if tab_index == 0 else 225, 15)


@pytest.fixture()
def router_env(monkeypatch):
    """Patch TabRegistry.get_tab + QTimer.singleShot (immediate) + insert hook."""
    from tabs.registry import TabRegistry

    tabs_by_type: dict = {}
    monkeypatch.setattr(
        TabRegistry, "get_tab", lambda self, st: tabs_by_type.get(st)
    )
    from PySide6.QtCore import QTimer

    monkeypatch.setattr(QTimer, "singleShot", staticmethod(lambda ms, fn: fn()))
    import events.image_carry as carry

    scheduled: list = []
    monkeypatch.setattr(
        carry, "_schedule_pending_insert",
        lambda st, ps: scheduled.append((st, list(ps))) or True,
    )
    return tabs_by_type, scheduled


def test_router_unknown_session_ignored(router_env):
    from ui.main_window.tab_strip_drop import deliver_gallery_drop

    _tabs_by_type, scheduled = router_env
    store = _FakeStore({}, active_id="sess-a")
    strip = _FakeStrip()
    assert deliver_gallery_drop(None, store, strip, _tab_pos(0), [Path("/x/a.png")]) is False
    assert scheduled == []


def test_router_declining_tab_ignored(router_env):
    from ui.main_window.tab_strip_drop import deliver_gallery_drop

    tabs_by_type, scheduled = router_env
    tabs_by_type["image_compare"] = SimpleNamespace(accepts_drop=lambda ps: False)
    store = _FakeStore(
        {"sess-a": _session("sess-a", "image_gallery"),
         "sess-b": _session("sess-b", "image_compare")},
        active_id="sess-a",
    )
    strip = _FakeStrip()
    assert deliver_gallery_drop(None, store, strip, _tab_pos(1), [Path("/x/a.png")]) is False
    assert scheduled == []
    assert strip.current is None  # no switch attempted


def test_router_own_gallery_tab_ignored(router_env):
    from ui.main_window.tab_strip_drop import deliver_gallery_drop

    tabs_by_type, scheduled = router_env
    tabs_by_type["image_gallery"] = SimpleNamespace(accepts_drop=lambda ps: True)
    store = _FakeStore(
        {"sess-a": _session("sess-a", "image_gallery")},
        active_id="sess-a",  # drop lands back on the source gallery tab
    )
    strip = _FakeStrip()
    assert deliver_gallery_drop(None, store, strip, _tab_pos(0), [Path("/x/a.png")]) is False
    assert scheduled == []


def test_router_drop_back_on_active_tab_ignored(router_env):
    """Target == active is the drag-source tab (source stays active mid-drag).

    Holds for any tab kind — the router names no session types (host
    sandbox), so the drop-back rule is purely positional.
    """
    from ui.main_window.tab_strip_drop import deliver_gallery_drop

    tabs_by_type, scheduled = router_env
    tabs_by_type["image_compare"] = SimpleNamespace(accepts_drop=lambda ps: True)
    store = _FakeStore(
        {"sess-a": _session("sess-a", "image_gallery"),
         "sess-b": _session("sess-b", "image_compare")},
        active_id="sess-b",  # compare tab active, drop lands back on it
    )
    strip = _FakeStrip()
    assert deliver_gallery_drop(None, store, strip, _tab_pos(1), [Path("/x/a.png")]) is False
    assert scheduled == []


def test_router_accepting_tab_switches_and_schedules(router_env):
    from ui.main_window.tab_strip_drop import deliver_gallery_drop

    tabs_by_type, scheduled = router_env
    tabs_by_type["image_compare"] = SimpleNamespace(accepts_drop=lambda ps: True)
    store = _FakeStore(
        {"sess-a": _session("sess-a", "image_gallery"),
         "sess-b": _session("sess-b", "image_compare")},
        active_id="sess-a",
    )
    strip = _FakeStrip()
    window = SimpleNamespace(presenter=None)  # → strip-fallback switch recipe
    assert deliver_gallery_drop(
        window, store, strip, _tab_pos(1), [Path("/x/a.png"), Path("/x/b.png")]
    ) is True
    assert strip.current == 1  # switched via setCurrentIndex fallback
    assert scheduled == [("image_compare", [Path("/x/a.png"), Path("/x/b.png")])]


def test_install_binds_handler_and_settles_without_paths(qapp, router_env, monkeypatch):
    from ui.main_window import tab_strip_drop as router

    bound: dict = {}

    class _Strip(_FakeStrip):
        def set_qdrag_drop_handler(self, handler):
            bound["handler"] = handler

    strip = _Strip()
    window = SimpleNamespace(ui=SimpleNamespace(workspace_tabs=strip))
    store = _FakeStore({}, active_id="sess-a")
    assert router.install_tab_strip_drop(window, store) is True
    assert callable(bound["handler"])

    # Plain mime (no gallery paths) → deliver False → event ignored, never lost.
    class _Ev:
        def __init__(self):
            self.ignored = False
            self.accepted = False

        def mimeData(self):
            return QMimeData()

        def ignore(self):
            self.ignored = True

        def accept(self):
            self.accepted = True

    monkeypatch.setattr("PySide6.QtGui.QCursor.pos", staticmethod(lambda: _tab_pos(0)))
    ev = _Ev()
    bound["handler"](ev)
    assert ev.ignored and not ev.accepted
