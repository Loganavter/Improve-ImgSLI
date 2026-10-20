"""Tiled pump backoff: full rate only on forward progress.

The residency loop used to pump a full-rate frame whenever a frame had
any drawn/resident tile — but a held level draws every frame, so a
plateaued stream (coverage never completing) spun ``update()`` at GUI-loop
rate forever: per-pump log spam plus an event loop too saturated for
resize drags. Pinned here:
- growing ``resident`` → immediate full-rate pump (streaming stays fast);
- plateaued ``resident`` → single throttled pump with backoff (no spin);
- per-pump logging is cover-timeline only (silent by default).
"""

from __future__ import annotations

import hashlib
import logging
from types import SimpleNamespace

import pytest


def _make_canvas(qtbot):
    from tabs.image_gallery.ui.quick_look import preview_canvas as pc

    card = pc.QuickLookCanvasWidget(None)
    qtbot.addWidget(card)
    card._tiled_source = ("k", object())
    return card


def _fake_renderer(result):
    calls: list = []

    class _R:
        def has_source(self):
            return True

        def render(self, *a, **k):
            calls.append(1)
            return result

        def store_size(self):
            return (64, 64)

    return _R(), calls


def _drive(canvas, monkeypatch, result, full_calls, slow_calls):
    from tabs.image_gallery.ui.quick_look import preview_canvas as pc

    renderer, _ = _fake_renderer(result)
    monkeypatch.setattr(canvas, "_ensure_tile_renderer", lambda: renderer)
    monkeypatch.setattr(
        pc.QuickLookCanvasWidget, "_pump_next_frame",
        lambda self: full_calls.append(1),
    )
    monkeypatch.setattr(
        pc.QuickLookCanvasWidget, "_pump_throttled",
        lambda self, stall: slow_calls.append(stall),
    )
    return canvas._render_tiled(object(), None, None, None, 64, 64)


def _result(drawn=True, covered=False, instances=3, resident=5):
    return SimpleNamespace(drawn=drawn, covered=covered, instances=instances, resident=resident)


def test_growing_resident_pumps_full_rate(qtbot, monkeypatch) -> None:
    card = _make_canvas(qtbot)
    full, slow = [], []
    assert _drive(card, monkeypatch, _result(resident=3), full, slow) is False
    assert _drive(card, monkeypatch, _result(resident=5), full, slow) is False
    assert len(full) == 2 and slow == []


def test_plateau_throttles_instead_of_spinning(qtbot, monkeypatch) -> None:
    card = _make_canvas(qtbot)
    full, slow = [], []
    assert _drive(card, monkeypatch, _result(resident=5), full, slow) is False
    assert len(full) == 1 and slow == []
    # Same tiles redrawn, coverage never completing: no more full-rate pumps.
    for _ in range(5):
        assert _drive(card, monkeypatch, _result(resident=5), full, slow) is False
    assert len(full) == 1
    assert len(slow) == 5


def test_idle_frame_pumps_nothing(qtbot, monkeypatch) -> None:
    card = _make_canvas(qtbot)
    full, slow = [], []
    assert _drive(card, monkeypatch, _result(drawn=False, resident=0), full, slow) is False
    assert full == [] and slow == []


# -- content-true backoff: a suppressed tick must not change the pixels -------
# Audit `audit-blind-test-inventory-2026-10-20` (blind pocket #2): the counts
# above are perf bounds, not correctness. A plateau tick that repainted a
# neighbour/stale plate, or that handed the pane over to a partly-resident
# tiled frame, kept every count assertion green while the user saw the wrong
# pixels. The assertions below decode the frame the canvas would present.


def _solid_store(rgb, size: int = 96):
    """Synthetic source: a solid-colour ``TiledPixelStore`` (distinct payload)."""
    pytest.importorskip("PIL")
    from PIL import Image as _PIL

    from engine.store.tiled_pixel_store import TiledPixelStore

    return TiledPixelStore.from_pil(_PIL.new("RGBA", (size, size), (*rgb, 255)))


def _frame_centre_rgb(frame):
    """Centre pixel of a canvas raster frame ``(w, h, RGBA bytes)``."""
    width, height, pixels = frame
    offset = ((height // 2) * width + (width // 2)) * 4
    return tuple(int(v) for v in pixels[offset : offset + 3])


def _frame_hash(frame) -> str:
    return hashlib.sha1(frame[2]).hexdigest()


def _target(size: int = 128):
    from PySide6.QtCore import QSize

    return SimpleNamespace(pixelSize=lambda: QSize(size, size))


def test_suppressed_tick_keeps_plate_pixels_and_focused_colour(qtbot, monkeypatch) -> None:
    """Plateau ticks hold the FOCUSED item's pixels, never the neighbour's.

    The raster plate is what the canvas presents while the tiled plan is not
    ``covered`` (``rhi_entry._render_tiled`` returns False). Bind it to the
    focused item (red) and drive the tiled source from a *different* colour
    (green): a suppressed tick that repaints, re-binds, or takes over early
    would surface green — every count/perf assertion would still pass.
    """
    focused, neighbour = (200, 20, 20), (20, 200, 20)
    card = _make_canvas(qtbot)
    card._active_composition = SimpleNamespace(
        layers=[SimpleNamespace(image=_solid_store(focused))]
    )
    # The tiled source is the NEIGHBOUR's image: whatever the hold path does
    # with it, the presented plate must stay the focused item's.
    card._tiled_source = ("neighbour", _solid_store(neighbour))
    before = card._raster_frame(_target())
    assert before is not None and _frame_centre_rgb(before) == focused
    before_hash = _frame_hash(before)

    renderer, calls = _fake_renderer(_result(drawn=True, covered=False, resident=5))
    monkeypatch.setattr(card, "_ensure_tile_renderer", lambda: renderer)
    full, slow = [], []
    monkeypatch.setattr(
        type(card), "_pump_next_frame", lambda self: full.append(1)
    )
    monkeypatch.setattr(
        type(card), "_pump_throttled", lambda self, stall: slow.append(stall)
    )

    for tick in range(5):
        # The tiled plan is never covered → no handover, the plate stays.
        assert (
            card._render_tiled(object(), None, None, None, 128, 128) is False
        ), f"tick {tick} handed the pane to an uncovered tiled frame"
        after = card._raster_frame(_target())
        assert after is not None
        assert _frame_hash(after) == before_hash, f"tick {tick} repainted the plate"
        assert _frame_centre_rgb(after) == focused, (
            f"tick {tick} shows {_frame_centre_rgb(after)}, "
            f"focused item is {focused} (neighbour {neighbour})"
        )
    # Counts stay as perf bounds: one full-rate pump, then backed-off retries.
    assert len(calls) == 5, "every suppressed tick still consulted the tiled source"
    assert len(full) == 1 and slow == [1, 2, 3, 4]
    assert card._tiled_source[0] == "neighbour", "the held source was not dropped"


def test_covered_tick_hands_over_and_changes_the_surface(qtbot, monkeypatch) -> None:
    """Discriminator for the hold above: a COVERED tick does take the pane.

    Without this, ``_render_tiled(...) is False`` could be true for any
    reason at all (a dead path), and the plateau assertion would be blind.
    """
    card = _make_canvas(qtbot)
    renderer, _calls = _fake_renderer(_result(drawn=True, covered=True, resident=5))
    monkeypatch.setattr(card, "_ensure_tile_renderer", lambda: renderer)
    monkeypatch.setattr(card, "_tiled_level_ready", lambda: True)
    monkeypatch.setattr(card, "_settle_present", lambda: None)
    full, slow = [], []
    monkeypatch.setattr(type(card), "_pump_next_frame", lambda self: full.append(1))
    monkeypatch.setattr(type(card), "_pump_throttled", lambda self, stall: slow.append(stall))
    assert card._render_tiled(object(), None, None, None, 128, 128) is True
    assert full == [] and slow == [], "a covered frame needs no pump"


def test_pump_log_silent_by_default(qtbot, monkeypatch, caplog) -> None:
    from tabs.image_gallery.ui.quick_look import preview_canvas as pc

    monkeypatch.delenv("IMGSLI_QL_COVER_DEBUG", raising=False)
    card = _make_canvas(qtbot)
    with caplog.at_level(logging.DEBUG, logger="ImproveImgSLI"):
        card._pump_next_frame()
    assert not [r for r in caplog.records if "pump posted" in r.getMessage()]


def test_pump_log_enabled_with_cover_flag(qtbot, monkeypatch, caplog) -> None:
    monkeypatch.setenv("IMGSLI_QL_COVER_DEBUG", "1")
    card = _make_canvas(qtbot)
    with caplog.at_level(logging.DEBUG, logger="ImproveImgSLI"):
        card._pump_next_frame()
    assert [r for r in caplog.records if "pump posted" in r.getMessage()]


def _drive_raising(canvas, monkeypatch, exc, full_calls, slow_calls):
    """Drive ``_render_tiled`` with a renderer whose ``render`` raises."""
    from tabs.image_gallery.ui.quick_look import preview_canvas as pc

    class _RaisingRenderer:
        def has_source(self):
            return True

        def render(self, *_a, **_k):
            raise exc

    monkeypatch.setattr(canvas, "_ensure_tile_renderer", lambda: _RaisingRenderer())
    monkeypatch.setattr(
        pc.QuickLookCanvasWidget, "_pump_next_frame",
        lambda self: full_calls.append(1),
    )
    monkeypatch.setattr(
        pc.QuickLookCanvasWidget, "_pump_throttled",
        lambda self, stall: slow_calls.append(stall),
    )
    return canvas._render_tiled(object(), None, None, None, 64, 64)


def test_failed_tiled_attempt_asks_for_a_backed_off_retry(qtbot, monkeypatch, caplog) -> None:
    """A raised attempt must not wait for an unrelated repaint.

    Live 2026-10-17: a series step failed its first two tiled frames and
    then sat on the raster plate until the next click, because nothing
    requested frame three. The retry here is throttled -- a failure that
    keeps repeating must not spin ``update()`` at GUI-loop rate.

    Driven with a plain exception so the retry itself is the falsifiable
    part (the typed ``MipCascadeNotReady`` case is covered next door and
    takes the same path).
    """
    monkeypatch.delenv("IMGSLI_QL_COVER_DEBUG", raising=False)
    card = _make_canvas(qtbot)
    full, slow = [], []
    with caplog.at_level(logging.DEBUG, logger="ImproveImgSLI"):
        assert _drive_raising(card, monkeypatch, RuntimeError("boom"), full, slow) is False
    assert slow == [1], "the failed attempt must request the retry"
    assert full == [], "and only a backed-off one"


def test_not_ready_attempt_is_not_logged_as_a_traceback(qtbot, monkeypatch, caplog) -> None:
    """``MipCascadeNotReady`` is "not ready yet", not a broken frame."""
    from engine.gpu.mip_cascade import MipCascadeNotReady

    monkeypatch.delenv("IMGSLI_QL_COVER_DEBUG", raising=False)
    card = _make_canvas(qtbot)
    exc = MipCascadeNotReady("Failed to create ql probe mip render target", attempt=1, details="x")
    full, slow = [], []
    with caplog.at_level(logging.DEBUG, logger="ImproveImgSLI"):
        assert _drive_raising(card, monkeypatch, exc, full, slow) is False
    assert not [
        r for r in caplog.records if "tiled frame failed open" in r.getMessage()
    ], "a transient cascade miss must not produce an exception traceback"
    assert slow == [1], "…and it still asks for the retry that can succeed"


def test_unknown_tiled_failure_keeps_its_traceback(qtbot, monkeypatch, caplog) -> None:
    """Anything else is still a real failure and must stay diagnosable."""
    monkeypatch.delenv("IMGSLI_QL_COVER_DEBUG", raising=False)
    card = _make_canvas(qtbot)
    with caplog.at_level(logging.DEBUG, logger="ImproveImgSLI"):
        _drive_raising(card, monkeypatch, RuntimeError("boom"), [], [])
    records = [r for r in caplog.records if "tiled frame failed open" in r.getMessage()]
    assert records and records[0].exc_info, "real failures keep the traceback"
