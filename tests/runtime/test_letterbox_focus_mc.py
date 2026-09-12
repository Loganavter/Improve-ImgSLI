"""Letterbox focus preservation for Multi Compare (W5 gap).

Inv: MC projection stack must preserve image focus across letterbox changes
just like IC's capture/restore focus rule.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from types import SimpleNamespace

from ui.canvas_infra.viewport.focus import capture_letterbox_focus, restore_letterbox_focus
from ui.canvas_infra.viewport.state import set_pan_offsets, set_zoom_level


def _mc_canvas(letterbox):
    # MC host mimics same runtime_state shape as IC
    return SimpleNamespace(
        runtime_state=SimpleNamespace(_letterbox_params=[letterbox]),
        zoom_level=None,
        pan_offset_x=None,
        pan_offset_y=None,
    )


def test_mc_letterbox_focus_preserved_after_letterbox_change():
    canvas = _mc_canvas((0.10, 0.0, 0.8, 1.0))
    set_zoom_level(canvas, 4.0)
    set_pan_offsets(canvas, 0.15, -0.07)
    focus = capture_letterbox_focus(canvas)
    assert focus is not None
    # Simulate resize that changes letterbox (e.g., window aspect change)
    canvas.runtime_state._letterbox_params[0] = (0.05, 0.02, 0.90, 0.96)
    assert restore_letterbox_focus(canvas, focus) is True
    assert capture_letterbox_focus(canvas) == focus


def test_mc_letterbox_focus_with_multiple_slots_independent():
    # MC has N slots sharing same canvas letterbox; each slot's pan is independent
    # Here we test that per-slot focus helpers (if they existed) would not cross-talk.
    # As proxy, verify that same capture/restore works when _letterbox_params holds MC-style value
    # and that changing one slot's pan does not affect another's focus representation.
    canvas1 = _mc_canvas((0.0, 0.0, 0.5, 1.0))
    canvas2 = _mc_canvas((0.5, 0.0, 0.5, 1.0))
    set_pan_offsets(canvas1, 0.2, 0.1)
    set_pan_offsets(canvas2, -0.3, 0.05)
    f1 = capture_letterbox_focus(canvas1)
    f2 = capture_letterbox_focus(canvas2)
    assert f1 != f2
    canvas1.runtime_state._letterbox_params[0] = (0.02, 0.0, 0.48, 1.0)
    canvas2.runtime_state._letterbox_params[0] = (0.52, 0.0, 0.48, 1.0)
    assert restore_letterbox_focus(canvas1, f1)
    assert restore_letterbox_focus(canvas2, f2)
    assert capture_letterbox_focus(canvas1) == f1
    assert capture_letterbox_focus(canvas2) == f2
