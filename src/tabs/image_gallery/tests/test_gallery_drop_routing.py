"""W12-D drop routing unify: zone and widget drops obey one accept rule.

Pins the frozen W12-D decisions:

* one accept rule everywhere — drops on the empty-state zone (forwarded with
  their full mime) behave identically to drops on the widget, via the shared
  ``shared/image_drop`` check;
* folders + batches handled uniformly on both surfaces (the zone label's own
  ``file_dropped(str)`` first-path-only emit no longer truncates live drops);
* the single-image special case is preserved intentionally: one image opens
  via ``open_paths([p])``, never its parent folder;
* file-vs-folder fallback is consistent (parent, never itself);
* non-image files are noted + ignored on both paths — never open the parent.

Headless-safe: real ``ImageGalleryWidget`` + fake controller, synthetic
``QDropEvent``/``QDragEnterEvent`` delivered via ``sendEvent`` (no real DnD).
"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QMimeData, QPoint, Qt, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QApplication, QWidget


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _mime(paths: list[Path]) -> QMimeData:
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(p)) for p in paths])
    return mime


def _drop_event(mime: QMimeData) -> QDropEvent:
    ev = QDropEvent(
        QPoint(5, 5), Qt.DropAction.CopyAction, mime,
        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
    )
    # QDropEvent keeps only a C++ pointer to the mime — hold a Python ref so
    # the QMimeData outlives delivery (else use-after-free segfaults).
    ev._mime_keepalive = mime  # type: ignore[attr-defined]
    return ev


def _drag_enter_event(mime: QMimeData) -> QDragEnterEvent:
    ev = QDragEnterEvent(
        QPoint(5, 5), Qt.DropAction.CopyAction, mime,
        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
    )
    ev._mime_keepalive = mime  # type: ignore[attr-defined]
    return ev


def _recorder():
    calls: dict = {"paths": [], "folders": [], "notes": []}
    ctrl = SimpleNamespace(
        open_paths=lambda ps: calls["paths"].append([Path(p) for p in ps]),
        open_folder=lambda f: calls["folders"].append(Path(f)),
    )
    return calls, ctrl


def _img(tmp_path: Path, name: str) -> Path:
    p = tmp_path / name
    p.write_bytes(b"\x89PNG\r\n\x1a\n")
    return p


def _widget_with_fake_ctrl(qtbot, calls_ctrl=None):
    from tabs.contract import TabContext
    from tabs.image_gallery.widget import ImageGalleryWidget

    calls, ctrl = calls_ctrl or _recorder()
    w = ImageGalleryWidget(None, context=TabContext())
    qtbot.addWidget(w)
    w._controller = ctrl  # type: ignore[attr-defined]
    w.resize(800, 600)
    w.show()
    zone = w._empty_state.findChild(QWidget, "gallery_empty_drop_zone")
    assert zone is not None
    return w, zone, calls, ctrl


def _deliver_via_zone_filter(w, zone, event) -> bool:
    """Deliver a synthetic DnD event the way live drops arrive.

    Spontaneous drops always pass installed event filters before the
    receiver — but Qt never delivers *synthetic* QDropEvent/QDragEnterEvent
    through the public dispatch APIs (sendEvent/postEvent/notify swallow
    them pre-filter), so tests invoke the installed zone filter directly.
    That filter object is exactly the seam this wave owns: installation is
    pinned by ``test_widget_installs_zone_forwarding``, routing here.
    """
    from PySide6.QtCore import QCoreApplication

    filt = w._zone_drop_filter
    assert filt is not None
    consumed = filt.eventFilter(zone, event)
    QCoreApplication.processEvents()
    return consumed


# --------------------------------------------------------------------------
# forwarding is installed; single-flight (no truncated re-emit)
# --------------------------------------------------------------------------


def test_widget_installs_zone_forwarding(qapp, qtbot, tmp_path):
    from tabs.image_gallery.ui import drag_drop as dnd

    w, zone, _calls, _ctrl = _widget_with_fake_ctrl(qtbot)
    assert getattr(w, "_zone_drop_filter", None) is not None
    # Idempotent: second install returns True and keeps the same filter.
    filt = w._zone_drop_filter
    assert dnd.install_zone_drop_forwarding(w) is True
    assert w._zone_drop_filter is filt


def test_zone_batch_drop_opens_all_without_truncation(qapp, qtbot, tmp_path):
    a = _img(tmp_path, "a.png")
    b = _img(tmp_path, "b.png")
    w, zone, calls, _ctrl = _widget_with_fake_ctrl(qtbot)

    dropped: list = []
    w._empty_state.fileDropped.connect(dropped.append)
    _deliver_via_zone_filter(w, zone, _drop_event(_mime([a, b])))

    # Whole batch via open_paths — the old paths[0]-only emit would open one.
    assert len(calls["paths"]) == 1
    assert {p.name for p in calls["paths"][0]} == {"a.png", "b.png"}
    assert calls["folders"] == []
    # Single-flight: the zone label never re-emitted its truncated signal.
    assert dropped == []


def test_zone_drop_matches_widget_drop_batch(qapp, qtbot, tmp_path):
    a = _img(tmp_path, "a.png")
    b = _img(tmp_path, "b.png")
    w, zone, zone_calls, _ctrl = _widget_with_fake_ctrl(qtbot)
    _deliver_via_zone_filter(w, zone, _drop_event(_mime([a, b])))

    w2_calls, w2_ctrl = _recorder()
    w2, _z2, _c2, _ct2 = _widget_with_fake_ctrl(qtbot, (w2_calls, w2_ctrl))
    w2.dropEvent(_drop_event(_mime([a, b])))

    assert zone_calls["paths"] == w2_calls["paths"]
    assert zone_calls["folders"] == w2_calls["folders"]


def test_zone_folder_drop_matches_widget_drop(qapp, qtbot, tmp_path):
    sub = tmp_path / "sub"
    sub.mkdir()
    w, zone, zone_calls, _ctrl = _widget_with_fake_ctrl(qtbot)
    _deliver_via_zone_filter(w, zone, _drop_event(_mime([sub])))

    w2_calls, w2_ctrl = _recorder()
    w2, _z2, _c2, _ct2 = _widget_with_fake_ctrl(qtbot, (w2_calls, w2_ctrl))
    w2.dropEvent(_drop_event(_mime([sub])))

    assert zone_calls["folders"] == [sub]
    assert zone_calls["folders"] == w2_calls["folders"]
    assert zone_calls["paths"] == w2_calls["paths"] == []


def test_zone_mixed_drop_rides_files_along(qapp, qtbot, tmp_path):
    img = _img(tmp_path, "pic.png")
    sub = tmp_path / "sub"
    sub.mkdir()
    w, zone, calls, _ctrl = _widget_with_fake_ctrl(qtbot)
    _deliver_via_zone_filter(w, zone, _drop_event(_mime([img, sub])))

    assert len(calls["paths"]) == 1
    assert {p.name for p in calls["paths"][0]} == {"pic.png", "sub"}
    assert calls["folders"] == []


# --------------------------------------------------------------------------
# shared accept rule on the zone surface (drag enter)
# --------------------------------------------------------------------------


def test_zone_drag_enter_accepts_images_rejects_non_images(qapp, qtbot, tmp_path):
    img = _img(tmp_path, "pic.png")
    txt = tmp_path / "readme.txt"
    txt.write_text("hi")
    w, zone, _calls, _ctrl = _widget_with_fake_ctrl(qtbot)

    ok = _drag_enter_event(_mime([img]))
    _deliver_via_zone_filter(w, zone, ok)
    assert ok.isAccepted()

    bad = _drag_enter_event(_mime([txt]))
    _deliver_via_zone_filter(w, zone, bad)
    assert not bad.isAccepted()


def test_non_image_drop_ignored_on_zone_and_widget(qapp, qtbot, tmp_path):
    from tabs.image_gallery.ui import drag_drop as dnd

    txt = tmp_path / "readme.txt"
    txt.write_text("hi")
    w, zone, calls, _ctrl = _widget_with_fake_ctrl(qtbot)
    ev = _drop_event(_mime([txt]))
    _deliver_via_zone_filter(w, zone, ev)
    assert not ev.isAccepted()
    assert calls["paths"] == [] and calls["folders"] == []

    # Signal path: noted + ignored — never opens the parent folder.
    noted: list = []
    owner = SimpleNamespace(
        _controller=SimpleNamespace(
            open_paths=lambda ps: calls["paths"].append(list(ps)),
            open_folder=lambda f: calls["folders"].append(f),
        ),
        set_folder_label=lambda p: noted.append(str(p)),
    )
    dnd.on_empty_file_dropped(owner, str(txt))
    assert calls["paths"] == [] and calls["folders"] == []
    assert len(noted) == 1


# --------------------------------------------------------------------------
# single-image special case (intentional, tested) + fallback consistency
# --------------------------------------------------------------------------


def test_single_image_opens_file_not_parent_on_both_paths(qapp, qtbot, tmp_path):
    from tabs.image_gallery.ui import drag_drop as dnd

    parent = tmp_path / "Imgs"
    parent.mkdir()
    single = _img(parent, "single.png")
    _img(parent, "other.png")

    w, zone, calls, _ctrl = _widget_with_fake_ctrl(qtbot)
    _deliver_via_zone_filter(w, zone, _drop_event(_mime([single])))
    assert len(calls["paths"]) == 1
    assert [p.name for p in calls["paths"][0]] == ["single.png"]
    assert calls["folders"] == []

    noted: list = []
    owner = SimpleNamespace(
        _controller=SimpleNamespace(
            open_paths=lambda ps: calls["paths"].append([Path(p) for p in ps]),
            open_folder=lambda f: calls["folders"].append(Path(f)),
        ),
        set_folder_label=lambda p: noted.append(str(p)),
    )
    dnd.on_empty_file_dropped(owner, str(single))
    assert len(calls["paths"]) == 2
    assert [p.name for p in calls["paths"][1]] == ["single.png"]
    assert calls["folders"] == []
    assert noted == []


def test_stray_path_falls_back_to_parent_not_itself(qapp, tmp_path):
    from tabs.image_gallery.ui import drag_drop as dnd

    fifo = tmp_path / "odd"
    os.mkfifo(fifo)
    calls, ctrl = _recorder()
    owner = SimpleNamespace(_controller=ctrl)
    dnd.on_empty_file_dropped(owner, str(fifo))
    # Parent, never the stray path itself (matches widget-path fallback).
    assert calls["folders"] == [tmp_path]
    assert dnd._fallback_folder([Path(fifo)]) == tmp_path
