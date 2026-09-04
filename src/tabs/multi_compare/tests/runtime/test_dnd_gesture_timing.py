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


def _event(mime):
    return SimpleNamespace(
        position=lambda: SimpleNamespace(toPoint=lambda: QPoint(10, 10)),
        mimeData=lambda: mime,
        acceptProposedAction=lambda: setattr(_event, "accepted", True),
        accept=lambda: None,
        ignore=lambda: None,
    )


def _widget():
    canvas = SimpleNamespace(
        mapFrom=lambda w, p: p,
        compute_drop_target=lambda pos, include_center=False: (None, None, True, None),
    )
    return SimpleNamespace(
        state=MultiCompareState(),
        canvas=canvas,
        store=SimpleNamespace(dispatch=MagicMock()),
    )


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
    assert "gesture leave: moves=4" in caplog.text
    assert "handler_avg=" in caplog.text
    assert "frames=0" in caplog.text
    assert widget.store.dispatch.call_count == 4 + 1  # previews + leave


def test_diag_light_move_skips_dispatch(monkeypatch, tmp_path):
    img = tmp_path / "a.png"
    img.write_bytes(b"x")
    monkeypatch.setenv("IMGSLI_MC_DND_DIAG_LIGHT_MOVE", "1")
    widget = _widget()
    accepted = []
    event = SimpleNamespace(
        mimeData=lambda: _mime([_url(img)]),
        acceptProposedAction=lambda: accepted.append(True),
        ignore=lambda: None,
    )
    drag_drop.drag_move_event(widget, event)
    assert accepted == [True]
    widget.store.dispatch.assert_not_called()


def test_diag_light_move_off_by_default(monkeypatch, tmp_path):
    monkeypatch.delenv("IMGSLI_MC_DND_DIAG_LIGHT_MOVE", raising=False)
    img = tmp_path / "a.png"
    img.write_bytes(b"x")
    widget = _widget()
    event = SimpleNamespace(
        position=lambda: SimpleNamespace(toPoint=lambda: QPoint(10, 10)),
        mimeData=lambda: _mime([_url(img)]),
        acceptProposedAction=lambda: None,
        ignore=lambda: None,
    )
    drag_drop.drag_move_event(widget, event)
    assert widget.store.dispatch.called


def test_summary_survives_missing_canvas_or_store():
    widget = SimpleNamespace()  # no canvas/store/timing at all
    drag_drop._timing_emit(widget, "leave")  # must not raise
    assert getattr(widget, "_dnd_timing", None) is None
    drag_drop._timing_add(widget, 1.0)  # must not raise
