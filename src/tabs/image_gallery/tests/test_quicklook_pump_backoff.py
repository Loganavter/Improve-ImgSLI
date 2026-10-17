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

import logging
from types import SimpleNamespace


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
