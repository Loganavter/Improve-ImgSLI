"""Timeline selection edge handles / move (toolkit TimelineWidget)."""

from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from sli_ui_toolkit.ui.widgets.composite.timeline_widget import interaction as ti


def _fake_widget(*, lo: int, hi: int, total: int = 100, left_gutter: int = 0):
    positions = {i: float(left_gutter + i * 10) for i in range(total)}

    def frame_to_pos(_widget, frame: int) -> float:
        return positions.get(int(frame), float(left_gutter + int(frame) * 10))

    def pos_to_frame(_widget, x: float) -> int:
        return max(0, min(total - 1, int(round((float(x) - left_gutter) / 10.0))))

    widget = SimpleNamespace(
        _has_selection=True,
        _anchor_index=lo,
        _drag_index=hi,
        _total_frames=total,
        LEFT_GUTTER=left_gutter,
        SELECTION_EDGE_HIT_PX=8,
        _selection_edit_mode=None,
        _selection_edit_origin_frame=0,
        _selection_edit_lo0=lo,
        _selection_edit_hi0=hi,
    )
    # Patch viewport helpers used by hit-testing / edit apply.
    import sli_ui_toolkit.ui.widgets.composite.timeline_widget.viewport as vp

    widget._frame_to_pos_impl = frame_to_pos
    widget._pos_to_frame_impl = pos_to_frame
    original_ftp = vp.frame_to_pos
    original_ptf = vp.pos_to_frame
    vp.frame_to_pos = frame_to_pos  # type: ignore[assignment]
    vp.pos_to_frame = pos_to_frame  # type: ignore[assignment]
    widget._restore = lambda: (
        setattr(vp, "frame_to_pos", original_ftp),
        setattr(vp, "pos_to_frame", original_ptf),
    )
    return widget


def test_selection_hit_zones_edges_and_body():
    widget = _fake_widget(lo=10, hi=40)
    try:
        # frame 10 → x=100, frame 40 → x=400
        assert ti.selection_hit_zone(widget, 100) == "resize_lo"
        assert ti.selection_hit_zone(widget, 400) == "resize_hi"
        assert ti.selection_hit_zone(widget, 250) == "move"
        assert ti.selection_hit_zone(widget, 50) is None
        assert ti.selection_hit_zone(widget, 500) is None
    finally:
        widget._restore()


def test_selection_move_keeps_width_and_clamps():
    widget = _fake_widget(lo=10, hi=30, total=50)
    try:
        widget._selection_edit_mode = "move"
        widget._selection_edit_origin_frame = 20
        widget._selection_edit_lo0 = 10
        widget._selection_edit_hi0 = 30
        ti._apply_selection_edit(widget, 25)  # +5
        assert (widget._anchor_index, widget._drag_index) == (15, 35)

        widget._selection_edit_origin_frame = 20
        widget._selection_edit_lo0 = 10
        widget._selection_edit_hi0 = 30
        ti._apply_selection_edit(widget, 5)  # would go negative → clamp
        assert widget._anchor_index == 0
        assert widget._drag_index == 20
    finally:
        widget._restore()


def test_selection_resize_edges():
    widget = _fake_widget(lo=10, hi=40)
    try:
        widget._selection_edit_mode = "resize_lo"
        widget._selection_edit_lo0 = 10
        widget._selection_edit_hi0 = 40
        ti._apply_selection_edit(widget, 18)
        assert (widget._anchor_index, widget._drag_index) == (18, 40)

        widget._selection_edit_mode = "resize_hi"
        widget._selection_edit_lo0 = 18
        widget._selection_edit_hi0 = 40
        ti._apply_selection_edit(widget, 28)
        assert (widget._anchor_index, widget._drag_index) == (18, 28)
    finally:
        widget._restore()
