"""Per-gesture DnD cost accounting (cursor-freeze diagnosis).

Each accepted gesture logs one summary line on leave/drop:
moves/handler-ms (hit-test + dispatch, measured in ``apply_drag_preview``)
vs frames/raster-ms (overlay raster, measured in the RHI pass). If the
cursor freezes while handler/raster averages are low, the stall is elsewhere
(cold init); if they are high, per-move dispatch+render starves the loop.
``IMGSLI_MC_DND_DIAG_LIGHT_MOVE`` short-circuits dragMove to accept-only
(image_compare semantics) as the decisive experiment.
"""

import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from PySide6.QtCore import QPoint

from tabs.multi_compare.models import MultiCompareState
from tabs.multi_compare.ui import drag_drop


def _mime(urls):
    mime = SimpleNamespace(
        hasUrls=lambda: bool(urls),
        hasFormat=lambda fmt: False,
        urls=lambda: urls,
    )
    return mime


def _url(path):
    return SimpleNamespace(toLocalFile=lambda: str(path))


def _event(mime, *, pos=QPoint(10, 10)):
    return SimpleNamespace(
        position=lambda: SimpleNamespace(toPoint=lambda: pos),
        mimeData=lambda: mime,
        acceptProposedAction=lambda: setattr(_event, "accepted", True),
        setDropAction=lambda action: setattr(_event, "drop_action", action),
        accept=lambda: None,
        ignore=lambda: None,
    )


def _widget(*, zoned=False):
    from tabs.multi_compare.scene.store import reduce

    calls: list = []

    def _compute(pos, include_center=False):
        if zoned and pos.x() >= 50:
            return ((1,), "right", False, None)
        return ((0,), "left", False, None)

    canvas = SimpleNamespace(
        mapFrom=lambda w, p: p,
        compute_drop_target=_compute,
    )
    widget = SimpleNamespace(
        state=MultiCompareState(),
        canvas=canvas,
        store=SimpleNamespace(),
        _pending_duplicate_source=None,
        _pending_paste_paths=None,
    )

    def _dispatch(action):
        # Standalone-like: apply the real reducer so the dispatch gate
        # compares against live state, like production bound mode does.
        widget.state = reduce(widget.state, action)
        calls.append(action)

    widget.store.dispatch = _dispatch
    widget.dispatched_calls = calls
    return widget


def test_gesture_summary_counts_moves_and_handler_cost(monkeypatch, tmp_path, caplog):
    img = tmp_path / "a.png"
    img.write_bytes(b"x")
    monkeypatch.setenv("IMGSLI_MC_DEBUG", "1")
    widget = _widget()
    mime = _mime([_url(img)])
    with caplog.at_level(logging.WARNING, logger="ImproveImgSLI"):
        drag_drop.drag_enter_event(widget, _event(mime))
        for _ in range(3):
            drag_drop.drag_move_event(widget, _event(mime))
        drag_drop.drag_leave_event(widget, _event(mime))
    assert "gesture leave: moves=4 dispatched=1 skipped=3" in caplog.text
    assert "handler_avg=" in caplog.text
    assert "frames=0" in caplog.text
    # enter + leave only: same-target moves dispatch nothing.
    assert len(widget.dispatched_calls) == 2


def test_zone_change_redispatches(monkeypatch, tmp_path, caplog):
    img = tmp_path / "a.png"
    img.write_bytes(b"x")
    monkeypatch.setenv("IMGSLI_MC_DEBUG", "1")
    widget = _widget(zoned=True)
    mime = _mime([_url(img)])
    with caplog.at_level(logging.WARNING, logger="ImproveImgSLI"):
        drag_drop.drag_enter_event(widget, _event(mime, pos=QPoint(10, 10)))
        drag_drop.drag_move_event(widget, _event(mime, pos=QPoint(80, 10)))
        drag_drop.drag_move_event(widget, _event(mime, pos=QPoint(80, 10)))
        drag_drop.drag_leave_event(widget, _event(mime))
    assert "gesture leave: moves=3 dispatched=2 skipped=1" in caplog.text
    assert len(widget.dispatched_calls) == 3  # enter + zone change + leave


def test_set_drag_state_noop_returns_same_instance():
    from tabs.multi_compare.scene import actions
    from tabs.multi_compare.scene.store import reduce

    state = MultiCompareState()
    same = actions.set_drag_state(
        active=True, internal=False, target_path=(0,), target_side="left"
    )
    once = reduce(state, same)
    assert once is not state
    assert reduce(once, same) is once  # identical payload → no new state

    changed = actions.set_drag_state(
        active=True, internal=False, target_path=(1,), target_side="left"
    )
    assert reduce(once, changed) is not once


def test_diag_light_move_skips_dispatch(monkeypatch, tmp_path):
    img = tmp_path / "a.png"
    img.write_bytes(b"x")
    monkeypatch.setenv("IMGSLI_MC_DND_DIAG_LIGHT_MOVE", "1")
    widget = _widget()
    accepted = []
    event = SimpleNamespace(
        mimeData=lambda: _mime([_url(img)]),
        acceptProposedAction=lambda: accepted.append(True),
        setDropAction=lambda action: accepted.append(("drop_action", action)),
        accept=lambda: accepted.append("accept"),
        ignore=lambda: None,
    )
    drag_drop.drag_move_event(widget, event)
    from PySide6.QtCore import Qt as _Qt

    assert ("drop_action", _Qt.DropAction.CopyAction) in accepted
    assert "accept" in accepted
    assert widget.dispatched_calls == []


def test_diag_light_move_off_by_default(monkeypatch, tmp_path):
    monkeypatch.delenv("IMGSLI_MC_DND_DIAG_LIGHT_MOVE", raising=False)
    img = tmp_path / "a.png"
    img.write_bytes(b"x")
    widget = _widget()
    event = SimpleNamespace(
        position=lambda: SimpleNamespace(toPoint=lambda: QPoint(10, 10)),
        mimeData=lambda: _mime([_url(img)]),
        acceptProposedAction=lambda: None,
        setDropAction=lambda action: None,
        accept=lambda: None,
        ignore=lambda: None,
    )
    drag_drop.drag_move_event(widget, event)
    assert widget.dispatched_calls != []


def test_summary_survives_missing_canvas_or_store():
    widget = SimpleNamespace()  # no canvas/store/timing at all
    drag_drop._timing_emit(widget, "leave")  # must not raise
    assert getattr(widget, "_dnd_timing", None) is None
    drag_drop._timing_add(widget, 1.0, True)  # must not raise
